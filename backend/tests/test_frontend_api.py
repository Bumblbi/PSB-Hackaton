from conftest import EvidenceLLM, authenticate
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from adapters.storage.database import persist_corpus
from apps.api.app.main import create_app
from apps.api.app.settings import Settings
from packages.legal_core.models import Corpus


def test_history_pagination_and_message_counts(corpus, tmp_path):
    settings = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'history.db'}")
    with TestClient(create_app(settings, corpus=corpus, llm=EvidenceLLM())) as client:
        authenticate(client)
        first = client.post("/api/v1/chats", json={"title": "Первый вопрос"}).json()["chat_id"]
        second = client.post("/api/v1/chats", json={"title": "Второй вопрос"}).json()["chat_id"]
        assert client.get("/api/v1/chats").json()["items"][0]["chat_id"] == second
        client.post(f"/api/v1/chats/{first}/messages", json={"question": "срок оплаты"})
        page = client.get("/api/v1/chats?limit=1").json()
        assert page["total"] == 2
        assert page["items"][0]["chat_id"] == first
        assert page["items"][0]["message_count"] == 2
        assert page["items"][0]["last_message_at"] is not None
        assert "messages" not in page["items"][0]
        assert client.get("/api/v1/chats?offset=1&limit=1").json()["items"][0]["chat_id"] == second
        assert client.get("/api/v1/chats?limit=101").status_code == 422
        assert client.get("/api/v1/chats?offset=-1").status_code == 422


def test_document_library_filters_active_versions(corpus, tmp_path):
    settings = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'sources.db'}")
    with TestClient(create_app(settings, corpus=corpus, llm=EvidenceLLM())) as client:
        authenticate(client)
        page = client.get("/api/v1/documents").json()
        assert page["total"] == 2
        assert all("chunks" not in item for item in page["items"])
        assert all(item["chunk_count"] > 0 for item in page["items"])
        filtered = client.get("/api/v1/documents", params={"kind": "amendment", "q": "ДОПОЛНЕНИЕ"})
        assert filtered.status_code == 200
        assert filtered.json()["total"] == 1
        document = filtered.json()["items"][0]
        detail = client.get(
            f"/api/v1/documents/{document['document_id']}",
            params={"version_id": document["version_id"]},
        )
        assert detail.status_code == 200
        assert len(detail.json()["sections"]) == document["chunk_count"]
        assert client.get("/api/v1/documents?offset=1&limit=1").json()["total"] == 2
        assert len(client.get("/api/v1/documents?offset=1&limit=1").json()["items"]) == 1
        assert client.get("/api/v1/documents?kind=unknown").status_code == 422
        assert client.get("/api/v1/documents?q=отсутствует").json()["items"] == []
        # An archived source remains addressable, but leaves the active library after restart.
        with Session(client.app.state.engine) as session, session.begin():
            persist_corpus(session, Corpus(versions=[corpus.versions[0]]))
    with TestClient(create_app(settings, llm=EvidenceLLM())) as client:
        authenticate(client)
        assert client.get("/api/v1/documents").json()["total"] == 1
        assert (
            client.get(
                f"/api/v1/documents/{document['document_id']}",
                params={"version_id": document["version_id"]},
            ).status_code
            == 200
        )
