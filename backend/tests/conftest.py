from pathlib import Path

import pytest

from adapters.ingest import ingest_manifest
from adapters.search.offline_index import OfflineIndex
from packages.legal_core.models import Claim, DraftAnswer, DraftCitation, Status


@pytest.fixture
def corpus():
    return ingest_manifest(Path("data/demo/manifest.json"))


@pytest.fixture
def index(corpus):
    return OfflineIndex(corpus)


class EvidenceLLM:
    """Deterministic test double; never selectable in application configuration."""

    def __init__(self, status=Status.ANSWERED, transform=None, supported=True):
        self.status, self.transform, self.supported = status, transform, supported
        self.requests = []

    def generate(self, request, evidence):
        self.requests.append(request)
        if not evidence or self.status in {
            Status.INSUFFICIENT_EVIDENCE,
            Status.OUT_OF_SCOPE,
            Status.DISALLOWED,
            Status.NEED_CLARIFICATION,
            Status.HISTORICAL_LAW_UNAVAILABLE,
        }:
            return DraftAnswer(
                status=self.status if evidence else Status.INSUFFICIENT_EVIDENCE,
                missing_info=["Тестовый недостающий источник"],
            )
        # Quote actual source text; the test double does not reason about law.
        chunk = next((c for c in evidence if "срок оплаты" in c.text), evidence[0])
        draft = DraftAnswer(
            status=self.status,
            claims=[
                Claim(
                    text=chunk.text,
                    citations=[DraftCitation(chunk_id=chunk.chunk_id, quote=chunk.text)],
                )
            ],
        )
        return self.transform(draft, evidence) if self.transform else draft

    def verify(self, claims, evidence):
        return [self.supported] * len(claims)


def authenticate(client):
    """Exercise real registration/login before testing authenticated application routes."""
    client.headers["X-Requested-With"] = "legal-workspace"
    credentials = {"email": "fixture@example.com", "password": "fixture password phrase 2026"}
    response = client.post("/api/v1/auth/register", json={"name": "Тестовый юрист", **credentials})
    if response.status_code == 409:
        response = client.post("/api/v1/auth/login", json=credentials)
    assert response.status_code in {200, 201}, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
