from typing import Protocol

from .models import Chunk, Claim, Corpus, DraftAnswer, Question


class SearchIndex(Protocol):
    corpus: Corpus

    def search(self, query: str, limit: int = 20) -> list[Chunk]: ...


class LLMGateway(Protocol):
    def generate(self, request: Question, evidence: list[Chunk]) -> DraftAnswer: ...

    def verify(self, claims: list[Claim], evidence: list[Chunk]) -> list[bool]: ...


class ProviderUnavailable(Exception):
    """Provider configuration, transport or response failure; never includes credentials."""
