"""Exercise database persistence and source-viewing API without an external LLM."""

from pathlib import Path

from fastapi.testclient import TestClient

from adapters.ingest import ingest_manifest
from apps.api.app.main import create_app
from apps.api.app.settings import Settings


def main():
    corpus = ingest_manifest(Path("data/demo/manifest.json"))
    settings = Settings(index_path=None, llm_provider="disabled")
    with TestClient(create_app(settings, corpus=corpus)) as client:
        assert client.get("/health").status_code == 200
        chat = client.post("/api/v1/chats", json={})
        assert chat.status_code == 201
        assert client.get("/api/v1/chats/" + chat.json()["chat_id"]).status_code == 200
        source = corpus.versions[0].chunks[0]
        assert client.get(f"/api/v1/chunks/{source.chunk_id}").status_code == 200
        doc = client.get(
            f"/api/v1/documents/{source.document_id}", params={"version_id": str(source.version_id)}
        )
        assert doc.status_code == 200
        response = client.post(
            f"/api/v1/chats/{chat.json()['chat_id']}/messages", json={"question": "срок оплаты"}
        )
        assert response.status_code == 503
        print("health, chat persistence, source viewing, unconfigured-provider rollback: OK")


if __name__ == "__main__":
    main()
