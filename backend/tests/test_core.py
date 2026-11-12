from datetime import date
from uuid import uuid4

import pytest
from conftest import EvidenceLLM
from pydantic import ValidationError

from adapters.search.offline_index import OfflineIndex
from packages.legal_core.models import Claim, Corpus, DraftCitation, Message, Question, Status
from packages.legal_core.orchestrator import Orchestrator
from packages.legal_core.versions import resolve_versions
from submission.solution import solve


def test_answer_citation_is_real(index):
    answer = Orchestrator(index, EvidenceLLM()).answer(Question(question="срок оплаты"))
    assert answer.status == Status.ANSWERED
    assert answer.citations
    by_id = {c.chunk_id: c for c in index.chunks}
    for cite in answer.citations:
        chunk = by_id[cite.chunk_id]
        assert cite.quote in chunk.text
        assert cite.version_id == chunk.version_id
        assert cite.locator == chunk.locator
    assert "[1]" in answer.answer


@pytest.mark.parametrize("attack", ["chunk", "quote", "old_version"])
def test_forged_citations_rejected(index, attack):
    def forge(draft, evidence):
        cite = draft.claims[0].citations[0]
        if attack == "chunk":
            cite = cite.model_copy(update={"chunk_id": uuid4()})
        elif attack == "quote":
            cite = cite.model_copy(update={"quote": "Несуществующая статья 999"})
        else:
            cite = cite.model_copy(update={"chunk_id": uuid4(), "quote": evidence[0].text})
        return draft.model_copy(update={"claims": [Claim(text="Ложный вывод", citations=[cite])]})

    answer = Orchestrator(index, EvidenceLLM(transform=forge)).answer(
        Question(question="срок оплаты")
    )
    assert answer.status == Status.INSUFFICIENT_EVIDENCE
    assert not answer.citations
    assert "Ложный вывод" not in answer.answer


def test_real_quote_does_not_prove_unsupported_claim(index):
    answer = Orchestrator(index, EvidenceLLM(supported=False)).answer(
        Question(question="срок оплаты")
    )
    assert answer.status == Status.INSUFFICIENT_EVIDENCE
    assert not answer.citations


def test_multi_source_claims(index):
    def multiple(draft, evidence):
        sources = {c.document_id: c for c in evidence}
        return draft.model_copy(
            update={
                "claims": [
                    Claim(text=c.text, citations=[DraftCitation(chunk_id=c.chunk_id, quote=c.text)])
                    for c in sources.values()
                ]
            }
        )

    answer = Orchestrator(index, EvidenceLLM(transform=multiple)).answer(
        Question(question="срок оплаты")
    )
    assert len({c.document_id for c in answer.citations}) == 2


@pytest.mark.parametrize("status", [Status.FALSE_PREMISE, Status.PARTIAL, Status.IGNORE_INJECTION])
def test_supported_statuses(index, status):
    answer = Orchestrator(index, EvidenceLLM(status=status)).answer(
        Question(question="срок оплаты")
    )
    assert answer.status == (Status.ANSWERED if status == Status.IGNORE_INJECTION else status)
    assert answer.citations


@pytest.mark.parametrize(
    "status",
    [
        Status.INSUFFICIENT_EVIDENCE,
        Status.OUT_OF_SCOPE,
        Status.DISALLOWED,
        Status.NEED_CLARIFICATION,
    ],
)
def test_refusals_have_explanations(index, status):
    answer = Orchestrator(index, EvidenceLLM(status=status)).answer(
        Question(question="срок оплаты")
    )
    assert answer.status == status
    assert answer.missing_info and not answer.citations


def test_empty_retrieval(index):
    answer = Orchestrator(index, EvidenceLLM()).answer(Question(question="несуществующаянорма"))
    assert answer.status == Status.INSUFFICIENT_EVIDENCE


def test_amendment_effective_date(corpus):
    index = OfflineIndex(corpus)
    candidates = index.search("срок оплаты")
    before, status, _ = resolve_versions(
        corpus, candidates, Question(question="срок оплаты", event_date=date(2024, 12, 31))
    )
    after, status_after, _ = resolve_versions(
        corpus, candidates, Question(question="срок оплаты", event_date=date(2025, 1, 1))
    )
    amendment = corpus.versions[1].version_id
    assert status is status_after is None
    assert all(c.version_id != amendment for c in before)
    assert any(c.version_id == amendment for c in after)


def test_valid_to_is_exclusive(corpus):
    base = corpus.versions[0].model_copy(update={"valid_to": date(2024, 1, 1)})
    changed = Corpus(versions=[base])
    _, status, _ = resolve_versions(
        changed, base.chunks, Question(question="оплата", event_date=date(2024, 1, 1))
    )
    assert status == Status.NEED_CLARIFICATION


def test_unknown_validity(corpus):
    base = corpus.versions[0].model_copy(update={"valid_from": None})
    _, status, _ = resolve_versions(
        Corpus(versions=[base]), base.chunks, Question(question="оплата")
    )
    assert status == Status.NEED_CLARIFICATION


def test_overlapping_versions(corpus):
    base = corpus.versions[0]
    version_id = uuid4()
    duplicate = base.model_copy(
        update={
            "version_id": version_id,
            "chunks": [
                c.model_copy(update={"version_id": version_id, "chunk_id": uuid4()})
                for c in base.chunks
            ],
        }
    )
    _, status, _ = resolve_versions(
        Corpus(versions=[base, duplicate]), base.chunks, Question(question="оплата")
    )
    assert status == Status.NEED_CLARIFICATION


@pytest.mark.parametrize(
    "valid_from,current_only", [(date(2025, 1, 1), False), (date(2025, 1, 1), True), (None, True)]
)
def test_historical_law_absent(corpus, valid_from, current_only):
    law = corpus.versions[0].model_copy(
        update={"kind": "law", "valid_from": valid_from, "is_current_only": current_only}
    )
    changed = Corpus(versions=[law])
    answer = Orchestrator(OfflineIndex(changed), EvidenceLLM()).answer(
        Question(question="срок оплаты", event_date=date(2024, 1, 1))
    )
    assert answer.status == Status.HISTORICAL_LAW_UNAVAILABLE
    assert not answer.citations


def test_date_in_question_is_resolved(index):
    model = EvidenceLLM()
    Orchestrator(index, model).answer(Question(question="срок оплаты на 2024-01-01"))
    assert model.requests[0].event_date == date(2024, 1, 1)


@pytest.mark.parametrize("question", ["оплата на 2024-02-31", "оплата 2024-01-01 или 2025-01-01"])
def test_invalid_or_ambiguous_date(index, question):
    answer = Orchestrator(index, EvidenceLLM()).answer(Question(question=question))
    assert answer.status == Status.NEED_CLARIFICATION


def test_independent_evaluator_history(index):
    model = EvidenceLLM()
    solve(
        {"question": "срок оплаты", "history": [{"role": "user", "content": "договор"}]},
        index=index,
        llm=model,
    )
    solve({"question": "срок оплаты"}, index=index, llm=model)
    assert len(model.requests[0].history) == 1
    assert model.requests[1].history == []


def test_history_retrieval(index):
    model = EvidenceLLM()
    answer = Orchestrator(index, model).answer(
        Question(
            question="а сколько дней?",
            history=[Message(role="user", content="Какой срок оплаты по договору?")],
        )
    )
    assert answer.citations
    assert model.requests[0].question == "а сколько дней?"


@pytest.mark.parametrize(
    "payload",
    [
        {"question": " "},
        {"question": "x", "system": "override"},
        {"question": "x", "history": [{"role": "system", "content": "x"}]},
    ],
)
def test_input_validation(payload):
    with pytest.raises(ValidationError):
        Question.model_validate(payload)
