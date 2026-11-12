import logging
import secrets
from contextlib import asynccontextmanager
from threading import Lock, RLock
from typing import Literal
from uuid import UUID, uuid4

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from adapters.ingest import ingest_manifest
from adapters.search.offline_index import OfflineIndex
from adapters.storage.database import (
    ActiveCorpusRow,
    ChatRow,
    ChunkRow,
    CitationRow,
    IngestRunRow,
    MessageRow,
    VersionRow,
    load_corpus,
    make_engine,
    persist_corpus,
    utcnow,
)
from adapters.storage.migrations import upgrade_database
from packages.legal_core.models import Answer, Corpus, Message, Question
from packages.legal_core.orchestrator import Orchestrator
from packages.legal_core.ports import ProviderUnavailable

from .factory import gateway
from .settings import Settings

logger = logging.getLogger("legal_api")


class ChatInput(BaseModel):
    title: str = Field(default="Новый чат", min_length=1, max_length=200)


class ReindexInput(BaseModel):
    corpus_path: str = Field(min_length=1, max_length=500)


def create_app(settings: Settings | None = None, *, llm=None, corpus: Corpus | None = None):
    settings = settings or Settings()
    engine = make_engine(settings.database_url)
    state_lock, reindex_lock = RLock(), Lock()
    # This MVP runs one API worker; Postgres also locks each chat across transactions.
    chat_lock = Lock()

    @asynccontextmanager
    async def lifespan(app):
        upgrade_database(engine)
        with Session(engine) as session, session.begin():
            initial = corpus
            if initial is None and settings.index_path and session.get(ActiveCorpusRow, 1) is None:
                initial = OfflineIndex.load(settings.index_path).corpus
            if initial is not None:
                persist_corpus(session, initial)
            loaded = load_corpus(session)
        app.state.index = OfflineIndex(loaded)
        app.state.llm = llm or gateway(settings, loaded)
        app.state.engine = engine
        yield
        engine.dispose()

    app = FastAPI(title="ПСБ Юридический ассистент", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Admin-Token"],
    )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        # FastAPI's default errors echo input; never echo chat text or credentials.
        return JSONResponse(status_code=422, content={"detail": "Некорректный формат запроса."})

    @app.exception_handler(ProviderUnavailable)
    async def provider_error(request, exc):
        return JSONResponse(
            status_code=503,
            content={
                "detail": "LLM недоступна или вернула некорректный ответ. Проверьте настройку провайдера."
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request, exc):
        return JSONResponse(status_code=503, content={"detail": "Хранилище временно недоступно."})

    @app.get("/health")
    def health():
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError:
            raise HTTPException(503, "Database unavailable") from None
        with state_lock:
            return {
                "status": "ok",
                "db": "ok",
                "redis": "disabled",
                "index_version": app.state.index.index_version,
                "chunks": len(app.state.index.chunks),
                "llm_provider": settings.llm_provider,
            }

    @app.post("/api/v1/chats", status_code=201)
    def create_chat(body: ChatInput):
        with Session(engine) as session, session.begin():
            chat = ChatRow(title=body.title)
            session.add(chat)
            session.flush()
            return {"chat_id": chat.id}

    @app.get("/api/v1/chats")
    def list_chats(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
        with Session(engine) as session:
            last_message = func.max(MessageRow.created_at)
            rows = session.execute(
                select(ChatRow, func.count(MessageRow.id), last_message)
                .outerjoin(MessageRow, MessageRow.chat_id == ChatRow.id)
                .group_by(ChatRow.id)
                .order_by(func.coalesce(last_message, ChatRow.created_at).desc(), ChatRow.id)
                .limit(limit)
                .offset(offset)
            ).all()
            return {
                "items": [
                    {
                        "chat_id": chat.id,
                        "title": chat.title,
                        "created_at": chat.created_at,
                        "last_message_at": last,
                        "message_count": count,
                    }
                    for chat, count, last in rows
                ],
                "total": session.scalar(select(func.count()).select_from(ChatRow)),
            }

    @app.get("/api/v1/documents")
    def list_documents(
        q: str = Query("", max_length=200),
        kind: Literal["law", "contract", "internal", "amendment"] | None = None,
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        with state_lock:
            versions = app.state.index.corpus.versions
            selected = sorted(
                (
                    version
                    for version in versions
                    if (kind is None or version.kind == kind)
                    and q.strip().casefold() in version.title.casefold()
                ),
                key=lambda version: (version.title.casefold(), version.revision),
            )
            return {
                "items": [
                    {
                        key: value
                        for key, value in version.model_dump(mode="json").items()
                        if key != "chunks"
                    }
                    | {"chunk_count": len(version.chunks)}
                    for version in selected[offset : offset + limit]
                ],
                "total": len(selected),
            }

    @app.get("/api/v1/chats/{chat_id}")
    def get_chat(chat_id: UUID):
        with Session(engine) as session:
            chat = session.get(ChatRow, str(chat_id))
            if not chat:
                raise HTTPException(404, "Chat not found")
            messages = session.scalars(
                select(MessageRow)
                .where(MessageRow.chat_id == str(chat_id))
                .order_by(MessageRow.ordinal)
            ).all()
            return {
                "chat_id": chat.id,
                "title": chat.title,
                "messages": [
                    {
                        "message_id": m.id,
                        "role": m.role,
                        "content": m.content,
                        "created_at": m.created_at,
                        "answer": m.answer_payload,
                    }
                    for m in messages
                ],
            }

    @app.post("/api/v1/chats/{chat_id}/messages", response_model=Answer)
    def send_message(chat_id: UUID, body: Question):
        with chat_lock, Session(engine) as session, session.begin():
            chat = session.scalar(
                select(ChatRow).where(ChatRow.id == str(chat_id)).with_for_update()
            )
            if chat is None:
                raise HTTPException(404, "Chat not found")
            stored = session.scalars(
                select(MessageRow)
                .where(MessageRow.chat_id == str(chat_id))
                .order_by(MessageRow.ordinal.desc())
                .limit(20)
            ).all()
            # A persisted chat has authoritative server history. Explicit history is allowed
            # only on the first turn (for an imported short conversation).
            if stored and body.history:
                raise HTTPException(400, "Use stored chat history or a new chat")
            history = [
                Message(role=m.role, content=m.content) for m in reversed(stored)
            ] or body.history
            request = body.model_copy(update={"history": history})
            with state_lock:
                index, provider = app.state.index, app.state.llm
            answer = Orchestrator(index, provider).answer(request)
            ordinal = stored[0].ordinal + 1 if stored else 0
            if not stored:
                for previous in body.history:
                    session.add(
                        MessageRow(
                            chat_id=str(chat_id),
                            role=previous.role,
                            content=previous.content,
                            ordinal=ordinal,
                        )
                    )
                    session.flush()
                    ordinal += 1
            session.add(
                MessageRow(
                    chat_id=str(chat_id), role="user", content=body.question, ordinal=ordinal
                )
            )
            session.flush()
            session.add(
                MessageRow(
                    id=str(answer.message_id),
                    chat_id=str(chat_id),
                    role="assistant",
                    ordinal=ordinal + 1,
                    content=answer.answer,
                    answer_payload=answer.model_dump(mode="json"),
                )
            )
            session.flush()
            for cite in answer.citations:
                session.add(
                    CitationRow(
                        message_id=str(answer.message_id),
                        chunk_id=str(cite.chunk_id),
                        quote=cite.quote,
                        locator=cite.locator,
                    )
                )
            logger.info(
                "answer trace_id=%s status=%s retrieval_ms=%s total_ms=%s",
                answer.trace_id,
                answer.status,
                answer.timings_ms.get("retrieval"),
                answer.timings_ms["total"],
            )
            return answer

    @app.get("/api/v1/documents/{document_id}")
    def get_document(document_id: UUID, version_id: UUID | None = None):
        with Session(engine) as session:
            rows = session.scalars(
                select(VersionRow).where(VersionRow.document_id == str(document_id))
            ).all()
            if not rows:
                raise HTTPException(404, "Document not found")
            if version_id is None and len(rows) > 1:
                raise HTTPException(400, "version_id is required for a versioned document")
            row = next((r for r in rows if version_id is None or r.id == str(version_id)), None)
            if not row:
                raise HTTPException(404, "Version not found")
            payload = row.payload
            return {
                "document_id": str(document_id),
                "title": payload["title"],
                "version": {k: v for k, v in payload.items() if k != "chunks"},
                "sections": payload["chunks"],
            }

    @app.get("/api/v1/chunks/{chunk_id}")
    def get_chunk(chunk_id: UUID):
        with Session(engine) as session:
            row = session.get(ChunkRow, str(chunk_id))
            if not row:
                raise HTTPException(404, "Chunk not found")
            version = session.get(VersionRow, row.version_id)
            return {
                "chunk_id": row.id,
                "document_id": version.document_id,
                "version_id": row.version_id,
                "locator": row.locator,
                "text": row.text,
            }

    def require_admin(token):
        expected = settings.admin_token.get_secret_value()
        if (
            settings.app_env != "development"
            or not expected
            or not secrets.compare_digest(token or "", expected)
        ):
            raise HTTPException(403, "Admin API disabled or unauthorized")

    def rebuild(job_id, manifest):
        try:
            imported = ingest_manifest(manifest)
            with state_lock, Session(engine) as session, session.begin():
                persist_corpus(session, imported)
                session.flush()
                updated = OfflineIndex(load_corpus(session))
                provider = llm or gateway(settings, updated.corpus)
                job = session.get(IngestRunRow, job_id)
                job.status, job.finished_at = "completed", utcnow()
                job.corpus_hash = updated.index_version
                job.stats_json = {
                    "versions": len(updated.corpus.versions),
                    "chunks": len(updated.chunks),
                }
            with state_lock:
                app.state.index, app.state.llm = updated, provider
        except Exception:  # noqa: BLE001 -- background job boundary must persist failure state
            # No paths, document contents, keys, or third-party exception bodies in logs.
            with Session(engine) as session, session.begin():
                job = session.get(IngestRunRow, job_id)
                job.status, job.finished_at = "failed", utcnow()
                job.stats_json = {
                    "error": "Import failed; validate manifest and immutable revisions."
                }
        finally:
            reindex_lock.release()

    @app.post("/api/v1/admin/reindex", status_code=202)
    def reindex(
        body: ReindexInput, tasks: BackgroundTasks, x_admin_token: str | None = Header(default=None)
    ):
        require_admin(x_admin_token)
        root = settings.corpus_root.resolve()
        manifest = (root / body.corpus_path).resolve()
        if (
            not manifest.is_relative_to(root)
            or not manifest.is_file()
            or manifest.suffix != ".json"
        ):
            raise HTTPException(400, "Manifest must be a JSON file inside CORPUS_ROOT")
        if not reindex_lock.acquire(blocking=False):
            raise HTTPException(409, "Reindex already running")
        job_id = str(uuid4())
        try:
            with Session(engine) as session, session.begin():
                session.add(IngestRunRow(id=job_id, status="running"))
        except Exception:
            reindex_lock.release()
            raise
        tasks.add_task(rebuild, job_id, manifest)
        return {"job_id": job_id}

    @app.get("/api/v1/admin/reindex/{job_id}")
    def reindex_status(job_id: UUID, x_admin_token: str | None = Header(default=None)):
        require_admin(x_admin_token)
        with Session(engine) as session:
            job = session.get(IngestRunRow, str(job_id))
            if not job:
                raise HTTPException(404, "Job not found")
            return {"job_id": job.id, "status": job.status, "stats": job.stats_json}

    return app


app = create_app()
