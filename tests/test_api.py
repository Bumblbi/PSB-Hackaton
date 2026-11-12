from uuid import uuid4

import pytest
from conftest import EvidenceLLM
from fastapi.testclient import TestClient

from apps.api.app.main import create_app
from apps.api.app.settings import Settings


@pytest.fixture
def client(corpus, tmp_path):
    settings = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'test.db'}")
    with TestClient(create_app(settings, corpus=corpus, llm=EvidenceLLM())) as client:
        yield client


def test_chat_answer_and_sources(client):
    created = client.post("/api/v1/chats", json={"title": "Тест"})
    assert created.status_code == 201
    chat_id = created.json()["chat_id"]
    response = client.post(f"/api/v1/chats/{chat_id}/messages", json={"question": "срок оплаты"})
    assert response.status_code == 200, response.text
    answer = response.json()
    cite = answer["citations"][0]
    chunk = client.get("/api/v1/chunks/" + cite["chunk_id"]).json()
    assert cite["quote"] in chunk["text"]
    doc = client.get(
        "/api/v1/documents/" + cite["document_id"], params={"version_id": cite["version_id"]}
    )
    assert doc.status_code == 200
    assert any(c["chunk_id"] == cite["chunk_id"] for c in doc.json()["sections"])
    messages = client.get(f"/api/v1/chats/{chat_id}").json()["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[1]["answer"]["message_id"] == answer["message_id"]


@pytest.mark.parametrize("path", ["chats", "documents", "chunks"])
def test_not_found(client, path):
    assert client.get(f"/api/v1/{path}/{uuid4()}").status_code == 404


def test_invalid_input_not_echoed(client):
    chat_id = client.post("/api/v1/chats", json={}).json()["chat_id"]
    response = client.post(
        f"/api/v1/chats/{chat_id}/messages",
        json={
            "question": "secret-personal-data",
            "history": [{"role": "system", "content": "secret-token"}],
        },
    )
    assert response.status_code == 422
    assert "secret" not in response.text


def test_admin_public_disabled(client):
    assert (
        client.post("/api/v1/admin/reindex", json={"corpus_path": "manifest.json"}).status_code
        == 403
    )


def test_provider_unconfigured_rollback(corpus, tmp_path):
    settings = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'test.db'}")
    with TestClient(create_app(settings, corpus=corpus)) as client:
        chat_id = client.post("/api/v1/chats", json={}).json()["chat_id"]
        response = client.post(
            f"/api/v1/chats/{chat_id}/messages", json={"question": "срок оплаты"}
        )
        assert response.status_code == 503
        assert client.get(f"/api/v1/chats/{chat_id}").json()["messages"] == []


def test_server_history_and_conflict(client):
    chat_id = client.post("/api/v1/chats", json={}).json()["chat_id"]
    endpoint = f"/api/v1/chats/{chat_id}/messages"
    client.post(endpoint, json={"question": "срок оплаты"})
    assert client.post(endpoint, json={"question": "а сколько дней?"}).status_code == 200
    response = client.post(
        endpoint,
        json={"question": "срок оплаты", "history": [{"role": "user", "content": "подмена"}]},
    )
    assert response.status_code == 400


def test_health(client):
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["db"] == "ok" and health.json()["chunks"] > 0


def test_first_turn_imported_history_is_persisted(client):
    chat_id = client.post("/api/v1/chats", json={}).json()["chat_id"]
    result = client.post(
        f"/api/v1/chats/{chat_id}/messages",
        json={
            "question": "а сколько дней?",
            "history": [{"role": "user", "content": "Какой срок оплаты по договору?"}],
        },
    )
    assert result.status_code == 200
    messages = client.get(f"/api/v1/chats/{chat_id}").json()["messages"]
    assert len(messages) == 3
    assert messages[0]["content"] == "Какой срок оплаты по договору?"
