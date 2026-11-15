"""Cookie sessions for the single-worker MVP, shared by SQLite and PostgreSQL."""

import hashlib
import secrets
import time
from datetime import UTC, timedelta
from threading import Lock

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator
from sqlalchemy import case, delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from adapters.storage.database import AuthSessionRow, AuthThrottleRow, UserRow, utcnow

from .validation import FieldValidationError

PASSWORDS = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
DUMMY_HASH = PASSWORDS.hash(secrets.token_urlsafe(32))


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr = Field(max_length=254)
    password: SecretStr = Field(min_length=1, max_length=128)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        return value.strip().casefold() if isinstance(value, str) else value


class Registration(Credentials):
    name: str = Field(min_length=1, max_length=100)
    password: SecretStr = Field(min_length=15, max_length=128)

    @field_validator("password")
    @classmethod
    def password_has_text(cls, value):
        if not value.get_secret_value().strip():
            raise ValueError("blank password")
        return value

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value):
        value = value.strip()
        if not value or any(ord(char) < 32 for char in value):
            raise ValueError("invalid name")
        return value


class PasswordChange(BaseModel):
    current_password: SecretStr = Field(min_length=1, max_length=128)
    new_password: SecretStr = Field(min_length=15, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_has_text(cls, value):
        if not value.get_secret_value().strip():
            raise ValueError("blank password")
        return value


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def csrf_token(token):
    return digest("csrf:" + token)


def public_user(user):
    return {"id": user.id, "email": user.email, "name": user.name}


def aware(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def password_valid(encoded, password):
    try:
        return PASSWORDS.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False


def build_auth(engine, settings):
    router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])
    cookie_name = "__Host-legal_session" if settings.auth_cookie_secure else "legal_session"
    # Serialize expensive hashes in the explicitly single-worker application.
    hash_lock = Lock()

    def browser_guard(request):
        if request.headers.get("x-requested-with") != "legal-workspace":
            raise HTTPException(403, "Требуется защищённый запрос приложения.")
        origin = request.headers.get("origin")
        trusted = {
            str(request.base_url).rstrip("/"),
            *settings.cors_origins,
            *settings.auth_trusted_origins,
        }
        if origin and origin not in trusted:
            raise HTTPException(403, "Недопустимый источник запроса.")
        if request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "Недопустимый источник запроса.")

    def throttle(request, action, email):
        now = int(time.time())
        address = request.client.host if request.client else "unknown"
        # Use the direct peer, never a client-supplied X-Forwarded-For.
        scopes = [("ip:" + address, 20 if action == "register" else 30), ("account:" + email, 10)]
        window = 3600 if action == "register" else 300
        with Session(engine) as db, db.begin():
            db.execute(delete(AuthThrottleRow).where(AuthThrottleRow.window_start < now - 86400))
            for scope, limit in scopes:
                key = digest(action + ":" + scope)
                insert = sqlite_insert if engine.dialect.name == "sqlite" else pg_insert
                statement = insert(AuthThrottleRow).values(key=key, window_start=now, attempts=1)
                expired = AuthThrottleRow.window_start <= now - window
                statement = statement.on_conflict_do_update(
                    index_elements=[AuthThrottleRow.key],
                    set_={
                        "window_start": case((expired, now), else_=AuthThrottleRow.window_start),
                        "attempts": case((expired, 1), else_=AuthThrottleRow.attempts + 1),
                    },
                ).returning(AuthThrottleRow.attempts)
                attempts = db.scalar(statement)
                if attempts > limit:
                    # Commit counters even when denying the request.
                    db.commit()
                    raise HTTPException(
                        429,
                        "Слишком много попыток. Попробуйте позже.",
                        headers={"Retry-After": str(window)},
                    )

    def require_user(request: Request):
        raw = request.cookies.get(cookie_name, "")
        if len(raw) != 64:
            raise HTTPException(401, "Войдите в учётную запись.")
        now = utcnow()
        with Session(engine, expire_on_commit=False) as db, db.begin():
            stored = db.get(AuthSessionRow, digest(raw))
            if (
                stored is None
                or aware(stored.expires_at) <= now
                or aware(stored.last_seen_at) + timedelta(minutes=settings.auth_idle_minutes) <= now
            ):
                raise HTTPException(401, "Сессия завершена. Войдите снова.")
            user = db.get(UserRow, stored.user_id)
            if user is None or not user.is_active:
                raise HTTPException(401, "Войдите в учётную запись.")
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                browser_guard(request)
                if not secrets.compare_digest(
                    request.headers.get("x-csrf-token", "").encode(), csrf_token(raw).encode()
                ):
                    raise HTTPException(403, "Проверка безопасности запроса не пройдена.")
            if (now - aware(stored.last_seen_at)).total_seconds() >= 60:
                stored.last_seen_at = now
            return user

    authenticated_user = Depends(require_user)

    def start_session(db, user, request, response):
        now = utcnow()
        db.execute(delete(AuthSessionRow).where(AuthSessionRow.expires_at <= now))
        old = request.cookies.get(cookie_name)
        if old:
            db.execute(delete(AuthSessionRow).where(AuthSessionRow.token_hash == digest(old)))
        # Bound persistent sessions per account.
        previous = db.scalars(
            select(AuthSessionRow)
            .where(AuthSessionRow.user_id == user.id)
            .order_by(AuthSessionRow.created_at.desc())
        ).all()
        for stale in previous[9:]:
            db.delete(stale)
        token = secrets.token_hex(32)
        age = settings.auth_session_hours * 3600
        db.add(
            AuthSessionRow(
                token_hash=digest(token), user_id=user.id, expires_at=now + timedelta(seconds=age)
            )
        )
        response.set_cookie(
            cookie_name,
            token,
            max_age=age,
            httponly=True,
            secure=settings.auth_cookie_secure,
            samesite="lax",
            path="/",
        )
        response.headers["Cache-Control"] = "no-store"
        return {"user": public_user(user), "csrf_token": csrf_token(token)}

    @router.post("/register", status_code=201)
    def register(body: Registration, request: Request, response: Response):
        browser_guard(request)
        throttle(request, "register", str(body.email))
        password = body.password.get_secret_value()
        with hash_lock:
            encoded = PASSWORDS.hash(password)
        try:
            with Session(engine) as db, db.begin():
                user = UserRow(email=str(body.email), name=body.name, password_hash=encoded)
                db.add(user)
                db.flush()
                return start_session(db, user, request, response)
        except IntegrityError:
            with Session(engine) as db:
                if (
                    db.scalar(select(UserRow.id).where(UserRow.email == str(body.email)))
                    is not None
                ):
                    raise FieldValidationError(
                        {"email": "Этот email уже используется. Войдите или укажите другой адрес"},
                        status_code=409,
                    ) from None
            raise

    @router.post("/login")
    def login(body: Credentials, request: Request, response: Response):
        browser_guard(request)
        throttle(request, "login", str(body.email))
        with hash_lock, Session(engine) as db, db.begin():
            user = db.scalar(select(UserRow).where(UserRow.email == str(body.email)))
            encoded = user.password_hash if user else DUMMY_HASH
            valid = password_valid(encoded, body.password.get_secret_value())
            if valid and user and PASSWORDS.check_needs_rehash(encoded):
                user.password_hash = PASSWORDS.hash(body.password.get_secret_value())
            if not valid or user is None or not user.is_active:
                raise FieldValidationError(
                    {"email": "Проверьте email и пароль", "password": "Проверьте email и пароль"},
                    status_code=401,
                    detail="Неверный email или пароль",
                )
            return start_session(db, user, request, response)

    @router.get("/session")
    def session_state(request: Request, response: Response, user=authenticated_user):
        response.headers["Cache-Control"] = "no-store"
        return {"user": public_user(user), "csrf_token": csrf_token(request.cookies[cookie_name])}

    @router.post("/logout", status_code=204)
    def logout(request: Request, response: Response, user=authenticated_user):
        with Session(engine) as db, db.begin():
            db.execute(
                delete(AuthSessionRow).where(
                    AuthSessionRow.token_hash == digest(request.cookies[cookie_name])
                )
            )
        response.delete_cookie(
            cookie_name, path="/", secure=settings.auth_cookie_secure, httponly=True, samesite="lax"
        )

    @router.post("/password", status_code=204)
    def change_password(body: PasswordChange, response: Response, user=authenticated_user):
        with hash_lock, Session(engine) as db, db.begin():
            stored = db.get(UserRow, user.id)
            if not password_valid(stored.password_hash, body.current_password.get_secret_value()):
                raise FieldValidationError(
                    {"current_password": "Текущий пароль указан неверно"},
                    status_code=400,
                )
            encoded = PASSWORDS.hash(body.new_password.get_secret_value())
            stored.password_hash = encoded
            db.execute(delete(AuthSessionRow).where(AuthSessionRow.user_id == user.id))
        response.delete_cookie(
            cookie_name, path="/", secure=settings.auth_cookie_secure, httponly=True, samesite="lax"
        )

    return router, require_user
