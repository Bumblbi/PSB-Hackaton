from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from adapters.storage.database import AuthSessionRow, AuthThrottleRow, UserRow, utcnow
from apps.api.app.auth import digest
from apps.api.app.main import create_app
from apps.api.app.settings import Settings

PASSWORD = "длинная парольная фраза 2026"


@pytest.fixture
def client(corpus, tmp_path):
    settings = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'auth.db'}")
    with TestClient(create_app(settings, corpus=corpus)) as client:
        client.headers["X-Requested-With"] = "legal-workspace"
        yield client


def register(client, email="lawyer@example.com"):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Юрист",
            "email": email,
            "password": PASSWORD,
        },
    )
    assert response.status_code == 201, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return response


def test_registration_hash_cookie_and_identity(client):
    response = register(client, " Lawyer@EXAMPLE.COM ")
    assert response.json()["user"]["email"] == "lawyer@example.com"
    assert set(response.json()["user"]) == {"id", "email", "name"}
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Path=/" in cookie
    token = client.cookies.get("legal_session")
    with Session(client.app.state.engine) as db:
        user = db.scalar(select(UserRow))
        assert user.password_hash.startswith("$argon2id$")
        assert PASSWORD not in user.password_hash
        stored = db.scalar(select(AuthSessionRow))
        assert stored.token_hash == digest(token)
        assert stored.token_hash != token
    session = client.get("/api/v1/auth/session")
    assert session.status_code == 200
    assert session.json() == response.json()
    assert session.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("password", ["short", "x" * 129, " " * 20])
def test_password_policy_and_redaction(client, password):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Юрист",
            "email": "user@example.com",
            "password": password,
        },
    )
    assert response.status_code == 422
    assert password not in response.text


def test_duplicate_email_and_generic_login_errors(client):
    register(client)
    duplicate = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Другой",
            "email": "LAWYER@EXAMPLE.COM",
            "password": PASSWORD,
        },
    )
    assert duplicate.status_code == 409
    responses = [
        client.post("/api/v1/auth/login", json={"email": email, "password": "wrong"})
        for email in ("lawyer@example.com", "unknown@example.com")
    ]
    assert [response.status_code for response in responses] == [401, 401]
    assert responses[0].json() == responses[1].json()


@pytest.mark.parametrize("path", ["chats", "documents", "chunks/" + str(uuid4())])
def test_anonymous_access_is_denied(client, path):
    assert client.get("/api/v1/" + path).status_code == 401
    assert client.post("/api/v1/chats", json={}).status_code == 401


def test_csrf_and_origin_checks(client):
    client.headers.pop("X-Requested-With")
    body = {"name": "Юрист", "email": "user@example.com", "password": PASSWORD}
    assert client.post("/api/v1/auth/register", json=body).status_code == 403
    client.headers["X-Requested-With"] = "legal-workspace"
    assert (
        client.post(
            "/api/v1/auth/register", json=body, headers={"Origin": "https://attacker.example"}
        ).status_code
        == 403
    )
    register(client)
    token = client.headers.pop("X-CSRF-Token")
    assert client.post("/api/v1/chats", json={}).status_code == 403
    assert client.post("/api/v1/auth/logout").status_code == 403
    assert (
        client.post("/api/v1/chats", json={}, headers={"X-CSRF-Token": "wrong"}).status_code == 403
    )
    client.headers["X-CSRF-Token"] = token
    assert (
        client.post(
            "/api/v1/chats", json={}, headers={"Origin": "https://attacker.example"}
        ).status_code
        == 403
    )
    assert (
        client.post("/api/v1/chats", json={}, headers={"Sec-Fetch-Site": "cross-site"}).status_code
        == 403
    )
    assert (
        client.post("/api/v1/chats", json={}, headers={"Origin": "http://testserver"}).status_code
        == 201
    )


def test_private_chats_and_logout_revocation(client):
    register(client)
    chat_id = client.post("/api/v1/chats", json={"title": "Частный вопрос"}).json()["chat_id"]
    old = client.cookies.get("legal_session")
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.get("/api/v1/chats").status_code == 401
    client.cookies.set("legal_session", old)
    assert client.get("/api/v1/auth/session").status_code == 401
    client.cookies.clear()
    register(client, "another@example.com")
    assert client.get("/api/v1/chats").json() == {"items": [], "total": 0}
    assert client.get(f"/api/v1/chats/{chat_id}").status_code == 404
    assert (
        client.post(
            f"/api/v1/chats/{chat_id}/messages", json={"question": "срок оплаты"}
        ).status_code
        == 404
    )


@pytest.mark.parametrize("expired", ["absolute", "idle"])
def test_session_timeouts(client, expired):
    register(client)
    with Session(client.app.state.engine) as db, db.begin():
        row = db.scalar(select(AuthSessionRow))
        if expired == "absolute":
            row.expires_at = utcnow() - timedelta(seconds=1)
        else:
            row.last_seen_at = utcnow() - timedelta(minutes=31)
    assert client.get("/api/v1/auth/session").status_code == 401


def test_rotation_and_password_change(client):
    register(client)
    old = client.cookies.get("legal_session")
    credentials = {"email": "lawyer@example.com", "password": PASSWORD}
    login = client.post("/api/v1/auth/login", json=credentials)
    assert login.status_code == 200
    assert old != client.cookies.get("legal_session")
    client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
    with Session(client.app.state.engine) as db:
        assert db.get(AuthSessionRow, digest(old)) is None
    changed = client.post(
        "/api/v1/auth/password",
        json={
            "current_password": PASSWORD,
            "new_password": "другая длинная парольная фраза 2027",
        },
    )
    assert changed.status_code == 204
    assert client.get("/api/v1/auth/session").status_code == 401
    assert client.post("/api/v1/auth/login", json=credentials).status_code == 401
    credentials["password"] = "другая длинная парольная фраза 2027"
    assert client.post("/api/v1/auth/login", json=credentials).status_code == 200


def test_persistent_login_throttle(client):
    for _ in range(10):
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "unknown@example.com",
                "password": "wrong",
            },
        )
        assert response.status_code == 401
    denied = client.post(
        "/api/v1/auth/login",
        json={
            "email": "unknown@example.com",
            "password": "wrong",
        },
    )
    assert denied.status_code == 429
    assert denied.headers["retry-after"] == "300"
    with Session(client.app.state.engine) as db:
        assert db.scalars(select(AuthThrottleRow)).all()


def test_disabled_user_and_legacy_chat(client):
    with client.app.state.engine.begin() as connection:
        connection.execute(
            text("INSERT INTO chats(id,title,created_at) VALUES (:id,'legacy',:now)"),
            {"id": str(uuid4()), "now": utcnow().isoformat()},
        )
    register(client)
    assert client.get("/api/v1/chats").json()["total"] == 0
    with Session(client.app.state.engine) as db, db.begin():
        db.scalar(select(UserRow)).is_active = False
    assert client.get("/api/v1/auth/session").status_code == 401


def test_secure_cookie_configuration(corpus, tmp_path):
    settings = Settings(
        _env_file=None, auth_cookie_secure=True, database_url=f"sqlite:///{tmp_path / 'secure.db'}"
    )
    with TestClient(create_app(settings, corpus=corpus), base_url="https://testserver") as client:
        client.headers["X-Requested-With"] = "legal-workspace"
        response = register(client)
        assert "__Host-legal_session=" in response.headers["set-cookie"]
        assert "Secure" in response.headers["set-cookie"]
        assert client.get("/api/v1/auth/session").status_code == 200


def test_registration_reports_all_invalid_fields_without_values(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "name": "   ",
            "email": "private-invalid-address",
            "password": "shhbad",
        },
    )
    assert response.status_code == 422
    errors = {item["field"]: item["message"] for item in response.json()["errors"]}
    assert set(errors) == {"name", "email", "password"}
    assert "name@example.ru" in errors["email"]
    assert "15" in errors["password"]
    assert "private-invalid-address" not in response.text
    assert "shhbad" not in response.text
    assert "input" not in response.text and "ctx" not in response.text


def test_missing_registration_fields_are_named(client):
    response = client.post("/api/v1/auth/register", json={})
    assert response.status_code == 422
    errors = {item["field"]: item["message"] for item in response.json()["errors"]}
    assert set(errors) == {"name", "email", "password"}
    assert "15" in errors["password"]


def test_login_error_marks_both_credentials(client):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "unknown@example.com",
            "password": "private-incorrect-password",
        },
    )
    assert response.status_code == 401
    assert {item["field"] for item in response.json()["errors"]} == {"email", "password"}
    assert "private-incorrect-password" not in response.text


def test_password_change_reports_current_password_field(client):
    register(client)
    response = client.post(
        "/api/v1/auth/password",
        json={
            "current_password": "private-wrong-password",
            "new_password": "valid long new password phrase",
        },
    )
    assert response.status_code == 400
    assert [item["field"] for item in response.json()["errors"]] == ["current_password"]
    assert "private-wrong-password" not in response.text


def test_question_errors_identify_date_question_and_document(client):
    register(client)
    chat = client.post("/api/v1/chats", json={}).json()["chat_id"]
    response = client.post(
        f"/api/v1/chats/{chat}/messages",
        json={
            "question": "   ",
            "event_date": "2026-02-31",
            "document_id": "private-invalid-id",
        },
    )
    assert response.status_code == 422
    assert {item["field"] for item in response.json()["errors"]} == {
        "question",
        "event_date",
        "document_id",
    }
    assert "private-invalid-id" not in response.text


def test_extra_field_names_are_not_echoed(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Юрист",
            "email": "valid@example.com",
            "password": PASSWORD,
            "private-extra-field": "private-extra-value",
        },
    )
    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "request"
    assert "private-extra" not in response.text
