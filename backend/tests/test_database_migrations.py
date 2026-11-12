import json
from pathlib import Path

from alembic import command
from alembic.config import Config
from conftest import EvidenceLLM
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from adapters.storage.database import ChunkRow, VersionRow, make_engine
from adapters.storage.migrations import upgrade_database
from apps.api.app.main import create_app
from apps.api.app.settings import Settings

ROOT = Path(__file__).resolve().parents[1]


def config():
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    return cfg


def test_upgrade_backfills_existing_sources(corpus, tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'old.db'}")
    version = corpus.versions[0]
    payload = version.model_dump(mode="json")
    payload["chunks"][0].update(page=2, embedding=[0.1, 0.2])
    with engine.begin() as connection:
        cfg = config()
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "0001")
        connection.execute(
            text("INSERT INTO documents VALUES (:id, :title, :kind)"),
            {"id": str(version.document_id), "title": version.title, "kind": version.kind},
        )
        connection.execute(
            text(
                "INSERT INTO document_versions "
                "(id, document_id, source_hash, payload) "
                "VALUES (:id, :doc, :hash, :payload)"
            ),
            {
                "id": str(version.version_id),
                "doc": str(version.document_id),
                "hash": version.source_hash,
                "payload": json.dumps(payload),
            },
        )
        for chunk in version.chunks:
            connection.execute(
                text("INSERT INTO chunks VALUES (:id, :version, :n, :loc, :body)"),
                {
                    "id": str(chunk.chunk_id),
                    "version": str(version.version_id),
                    "n": chunk.ordinal,
                    "loc": chunk.locator,
                    "body": chunk.text,
                },
            )
    upgrade_database(engine)
    upgrade_database(engine)
    with Session(engine) as session:
        row = session.get(VersionRow, str(version.version_id))
        assert row.revision == version.revision
        assert row.source_name == version.source_name
        assert row.payload == payload
        chunk = session.get(ChunkRow, str(version.chunks[0].chunk_id))
        assert chunk.page == 2
        assert chunk.embedding == [0.1, 0.2]
        assert chunk.text == version.chunks[0].text
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.check(cfg)
    assert "eval_runs" in inspect(engine).get_table_names()
    engine.dispose()


def test_alembic_uses_same_dotenv_database_as_api(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    database = tmp_path / "configured.db"
    (tmp_path / ".env").write_text(f"DATABASE_URL=sqlite:///{database}\n", encoding="utf-8")
    command.upgrade(config(), "head")
    engine = make_engine(Settings().database_url)
    assert "messages" in inspect(engine).get_table_names()
    assert database.exists()
    assert not (tmp_path / "legal.db").exists()
    engine.dispose()


def test_api_restart_preserves_chat_and_citations(corpus, tmp_path):
    settings = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'api.db'}")
    with TestClient(create_app(settings, corpus=corpus, llm=EvidenceLLM())) as client:
        chat_id = client.post("/api/v1/chats", json={}).json()["chat_id"]
        response = client.post(
            f"/api/v1/chats/{chat_id}/messages",
            json={"question": "срок оплаты", "event_date": "2024-01-01"},
        )
        assert response.status_code == 200
        answer = response.json()
        assert answer["citations"]
    with TestClient(create_app(settings, llm=EvidenceLLM())) as client:
        assert client.get("/health").json()["db"] == "ok"
        stored = client.get(f"/api/v1/chats/{chat_id}").json()["messages"]
        assert stored[-1]["answer"] == answer
        citation = answer["citations"][0]
        source = client.get(f"/api/v1/chunks/{citation['chunk_id']}").json()
        assert citation["quote"] in source["text"]
        with client.app.state.engine.connect() as connection:
            assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0002"
