from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from packages.legal_core.models import Corpus


def utcnow():
    return datetime.now(UTC)


def new_id():
    return str(uuid4())


JSON_DATA = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class DocumentRow(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(30))


class ActiveCorpusRow(Base):
    __tablename__ = "active_corpus"
    id: Mapped[int] = mapped_column(primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON_DATA)


class VersionRow(Base):
    __tablename__ = "document_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    revision: Mapped[str] = mapped_column(String(200), server_default="")
    source_name: Mapped[str] = mapped_column(Text, server_default="")
    is_current_only: Mapped[bool] = mapped_column(Boolean, server_default="false")
    source_hash: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict] = mapped_column(JSON_DATA)


class ChunkRow(Base):
    __tablename__ = "chunks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    version_id: Mapped[str] = mapped_column(ForeignKey("document_versions.id"), index=True)
    ordinal: Mapped[int]
    locator: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(JSON_DATA, nullable=True)


class DocumentLinkRow(Base):
    __tablename__ = "document_links"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    parent_document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"))
    related_document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"))
    relation_type: Mapped[str] = mapped_column(String(30), default="amendment")


class ChatRow(Base):
    __tablename__ = "chats"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(200), default="Новый чат")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MessageRow(Base):
    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("chat_id", "ordinal", name="uq_messages_chat_ordinal"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    chat_id: Mapped[str] = mapped_column(ForeignKey("chats.id"), index=True)
    ordinal: Mapped[int]
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    answer_payload: Mapped[dict | None] = mapped_column(JSON_DATA, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CitationRow(Base):
    __tablename__ = "answer_citations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id"), index=True)
    chunk_id: Mapped[str] = mapped_column(ForeignKey("chunks.id"))
    quote: Mapped[str] = mapped_column(Text)
    locator: Mapped[str] = mapped_column(Text)


class IngestRunRow(Base):
    __tablename__ = "ingest_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20))
    corpus_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stats_json: Mapped[dict] = mapped_column(JSON_DATA, default=dict)


class EvalRunRow(Base):
    __tablename__ = "eval_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    test_id: Mapped[str] = mapped_column(String(200), index=True)
    answer_status: Mapped[str] = mapped_column(String(40))
    duration_ms: Mapped[float]
    checks_json: Mapped[dict] = mapped_column(JSON_DATA, default=dict)


Index("ix_versions_validity", VersionRow.document_id, VersionRow.valid_from)


def make_engine(url: str):
    options = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
    engine = create_engine(url, pool_pre_ping=True, **options)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

    return engine


def persist_corpus(session: Session, corpus: Corpus):
    # Append-only versions preserve citations to earlier messages across reindexing.
    for v in corpus.versions:
        session.merge(DocumentRow(id=str(v.document_id), title=v.title, kind=v.kind))
    session.flush()
    for v in corpus.versions:
        payload = v.model_dump(mode="json")
        existing = session.get(VersionRow, str(v.version_id))
        if existing:
            if existing.payload != payload:
                raise ValueError("existing version IDs are immutable; use a new revision")
            continue
        session.add(
            VersionRow(
                id=str(v.version_id),
                document_id=str(v.document_id),
                valid_from=v.valid_from,
                valid_to=v.valid_to,
                revision=v.revision,
                source_name=v.source_name,
                is_current_only=v.is_current_only,
                source_hash=v.source_hash,
                payload=payload,
            )
        )
        session.flush()
        for c in v.chunks:
            session.add(
                ChunkRow(
                    id=str(c.chunk_id),
                    version_id=str(v.version_id),
                    ordinal=c.ordinal,
                    locator=c.locator,
                    text=c.text,
                    page=c.page,
                    embedding=c.embedding,
                )
            )
        if v.amends_document_id:
            session.merge(
                DocumentLinkRow(
                    id=str(v.version_id),
                    parent_document_id=str(v.amends_document_id),
                    related_document_id=str(v.document_id),
                )
            )
    session.merge(ActiveCorpusRow(id=1, payload=corpus.model_dump(mode="json")))


def load_corpus(session: Session) -> Corpus:
    active = session.get(ActiveCorpusRow, 1)
    return Corpus.model_validate(active.payload) if active else Corpus()
