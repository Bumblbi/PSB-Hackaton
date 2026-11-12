import json

from conftest import EvidenceLLM
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.storage.database import ChunkRow, load_corpus, persist_corpus
from apps.api.app.main import create_app
from apps.api.app.settings import Settings
from packages.legal_core.models import Corpus


def test_reindex_archives_sources_but_replaces_active_corpus(corpus, tmp_path):
    settings = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'test.db'}")
    with TestClient(create_app(settings, corpus=corpus, llm=EvidenceLLM())) as client:
        engine = client.app.state.engine
        with Session(engine) as session, session.begin():
            persist_corpus(session, Corpus(versions=[corpus.versions[0]]))
        with Session(engine) as session:
            active = load_corpus(session)
            assert len(active.versions) == 1
            old = session.scalar(
                select(ChunkRow).where(ChunkRow.id == str(corpus.versions[1].chunks[0].chunk_id))
            )
            assert old is not None


def test_admin_reindex_and_restart_persist_active(corpus, tmp_path):
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "a.txt").write_text("1. Синтетический срок оплаты 7 дней.", encoding="utf-8")
    manifest = {
        "documents": [
            {
                "key": "new",
                "revision": "1",
                "title": "Договор",
                "kind": "contract",
                "path": "a.txt",
                "valid_from": "2020-01-01",
            }
        ]
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        corpus_root=root,
        app_env="development",
        admin_token=SecretStr("test-admin"),
    )
    headers = {"X-Admin-Token": "test-admin"}
    with TestClient(create_app(settings, corpus=corpus, llm=EvidenceLLM())) as client:
        assert (
            client.post("/api/v1/admin/reindex", json={"corpus_path": "manifest.json"}).status_code
            == 403
        )
        assert (
            client.post(
                "/api/v1/admin/reindex", headers=headers, json={"corpus_path": "../outside.json"}
            ).status_code
            == 400
        )
        result = client.post(
            "/api/v1/admin/reindex", headers=headers, json={"corpus_path": "manifest.json"}
        )
        assert result.status_code == 202
        job_id = result.json()["job_id"]
        job = client.get("/api/v1/admin/reindex/" + job_id, headers=headers).json()
        assert job["status"] == "completed"
        assert client.get("/health").json()["chunks"] == 1
    # An index path is only the bootstrap source, never an override of a successful reindex.
    from adapters.search.offline_index import OfflineIndex

    index_path = tmp_path / "bootstrap.json"
    OfflineIndex(corpus).save(index_path)
    settings = settings.model_copy(update={"index_path": index_path})
    with TestClient(create_app(settings, llm=EvidenceLLM())) as client:
        assert client.get("/health").json()["chunks"] == 1


def test_failed_reindex_keeps_active_snapshot(corpus, tmp_path):
    (tmp_path / "bad.json").write_text("{}", encoding="utf-8")
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        corpus_root=tmp_path,
        app_env="development",
        admin_token=SecretStr("test-admin"),
    )
    headers = {"X-Admin-Token": "test-admin"}
    with TestClient(create_app(settings, corpus=corpus, llm=EvidenceLLM())) as client:
        before = client.get("/health").json()["index_version"]
        result = client.post(
            "/api/v1/admin/reindex", headers=headers, json={"corpus_path": "bad.json"}
        )
        job = client.get("/api/v1/admin/reindex/" + result.json()["job_id"], headers=headers)
        assert job.json()["status"] == "failed"
        assert client.get("/health").json()["index_version"] == before
