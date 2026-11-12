from datetime import date
from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Status(StrEnum):
    ANSWERED = "ANSWERED"
    PARTIAL = "PARTIAL"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    NEED_CLARIFICATION = "NEED_CLARIFICATION"
    FALSE_PREMISE = "FALSE_PREMISE"
    HISTORICAL_LAW_UNAVAILABLE = "HISTORICAL_LAW_UNAVAILABLE"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    DISALLOWED = "DISALLOWED"
    IGNORE_INJECTION = "IGNORE_INJECTION"


class Chunk(Model):
    chunk_id: UUID
    document_id: UUID
    version_id: UUID
    ordinal: int = Field(ge=0)
    locator: str = Field(min_length=1)
    text: str = Field(min_length=1)
    page: int | None = Field(default=None, ge=1)
    embedding: list[float] | None = None


class DocumentVersion(Model):
    version_id: UUID
    document_id: UUID
    title: str = Field(min_length=1)
    kind: Literal["law", "contract", "internal", "amendment"]
    revision: str = Field(min_length=1)
    source_name: str
    source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    valid_from: date | None = None
    valid_to: date | None = None
    is_current_only: bool = False
    amends_document_id: UUID | None = None
    chunks: list[Chunk] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_version(self):
        if self.valid_to and (not self.valid_from or self.valid_to <= self.valid_from):
            raise ValueError("valid_to must follow valid_from")
        if self.kind == "amendment" and not self.amends_document_id:
            raise ValueError("amendment requires amends_document_id")
        if len({c.chunk_id for c in self.chunks}) != len(self.chunks):
            raise ValueError("duplicate chunk ID")
        if any(
            c.version_id != self.version_id or c.document_id != self.document_id
            for c in self.chunks
        ):
            raise ValueError("chunk/version identity mismatch")
        return self


class Corpus(Model):
    schema_version: Literal[1] = 1
    embedding_model: str | None = None
    versions: list[DocumentVersion] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_ids(self):
        versions = [v.version_id for v in self.versions]
        chunks = [c.chunk_id for v in self.versions for c in v.chunks]
        if len(set(versions)) != len(versions) or len(set(chunks)) != len(chunks):
            raise ValueError("duplicate corpus IDs")
        documents = {v.document_id for v in self.versions}
        for v in self.versions:
            if v.amends_document_id and v.amends_document_id not in documents:
                raise ValueError("amendment target is missing")
        return self


class Message(Model):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=16000)


class Question(Model):
    question: str = Field(min_length=1, max_length=8000)
    event_date: date | None = None
    document_id: UUID | None = None
    document_kind: Literal["law", "contract", "internal", "amendment"] | None = None
    history: list[Message] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def not_blank(self):
        if not self.question.strip():
            raise ValueError("question must not be blank")
        return self


class DraftCitation(Model):
    chunk_id: UUID
    quote: str = Field(min_length=1, max_length=6000)


class Claim(Model):
    text: str = Field(min_length=1, max_length=4000)
    citations: list[DraftCitation] = Field(min_length=1, max_length=8)


class DraftAnswer(Model):
    status: Status
    claims: list[Claim] = Field(default_factory=list, max_length=20)
    reason: str = Field(default="", max_length=2000)
    missing_info: list[str] = Field(default_factory=list, max_length=10)
    clarifying_question: str | None = Field(default=None, max_length=1000)


class Citation(Model):
    ref: int
    document_id: UUID
    version_id: UUID
    chunk_id: UUID
    locator: str
    quote: str


class Answer(Model):
    message_id: UUID = Field(default_factory=uuid4)
    status: Status
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    reason: str = ""
    missing_info: list[str] = Field(default_factory=list)
    clarifying_question: str | None = None
    trace_id: UUID = Field(default_factory=uuid4)
    timings_ms: dict[str, float] = Field(default_factory=dict)
