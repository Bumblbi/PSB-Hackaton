"""Run against the real local Compose stack, including session persistence on restart."""

import secrets
import subprocess
import time
from uuid import uuid4

import httpx


def main():
    origin = "http://127.0.0.1:8080"
    headers = {"X-Requested-With": "legal-workspace", "Origin": origin}
    password = secrets.token_urlsafe(32)
    email = f"compose.{uuid4()}@example.com"
    with httpx.Client(base_url=origin, headers=headers, timeout=15) as owner:
        assert owner.get("/").status_code == 200
        assert owner.get("/health").json()["db"] == "ok"
        assert owner.get("/api/v1/chats").status_code == 401
        created = owner.post(
            "/api/v1/auth/register",
            json={
                "name": "Проверка Docker",
                "email": email,
                "password": password,
            },
        )
        assert created.status_code == 201, created.text
        identity = created.json()["user"]
        owner.headers["X-CSRF-Token"] = created.json()["csrf_token"]
        chat = owner.post("/api/v1/chats", json={"title": "Проверка сохранения Docker"})
        assert chat.status_code == 201
        chat_id = chat.json()["chat_id"]
        sources = owner.get("/api/v1/documents")
        assert sources.status_code == 200
        assert sources.json()["items"]
        csrf = owner.headers.pop("X-CSRF-Token")
        assert owner.post("/api/v1/chats", json={}).status_code == 403
        owner.headers["X-CSRF-Token"] = csrf
        with httpx.Client(base_url=origin, headers=headers, timeout=15) as other:
            second = other.post(
                "/api/v1/auth/register",
                json={
                    "name": "Другой пользователь Docker",
                    "email": f"compose.{uuid4()}@example.com",
                    "password": secrets.token_urlsafe(32),
                },
            )
            assert second.status_code == 201
            other.headers["X-CSRF-Token"] = second.json()["csrf_token"]
            assert other.get(f"/api/v1/chats/{chat_id}").status_code == 404
            assert other.get("/api/v1/chats").json()["total"] == 0
            assert other.post("/api/v1/auth/logout").status_code == 204
        subprocess.run(
            ["docker", "compose", "restart", "api"], check=True, capture_output=True, timeout=60
        )
        deadline = time.monotonic() + 60
        while True:
            try:
                if owner.get("/health").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if time.monotonic() > deadline:
                raise RuntimeError("API did not recover after restart")
            time.sleep(1)
        assert owner.get("/api/v1/auth/session").json()["user"] == identity
        assert owner.get(f"/api/v1/chats/{chat_id}").status_code == 200
        new_password = secrets.token_urlsafe(32)
        assert (
            owner.post(
                "/api/v1/auth/password",
                json={
                    "current_password": password,
                    "new_password": new_password,
                },
            ).status_code
            == 204
        )
        assert owner.get("/api/v1/auth/session").status_code == 401
        assert (
            owner.post(
                "/api/v1/auth/login",
                json={
                    "email": email,
                    "password": password,
                },
            ).status_code
            == 401
        )
        login = owner.post("/api/v1/auth/login", json={"email": email, "password": new_password})
        assert login.status_code == 200
        owner.headers["X-CSRF-Token"] = login.json()["csrf_token"]
        assert owner.post("/api/v1/auth/logout").status_code == 204
        assert owner.get("/api/v1/chats").status_code == 401
    print(
        "Compose: nginx, API, registration, cookies, CSRF, isolation, restart persistence, password change, logout OK"
    )


if __name__ == "__main__":
    main()
