import json
from pathlib import Path
from uuid import uuid4

import pytest
from conftest import EvidenceLLM

from adapters.search.offline_index import OfflineIndex
from packages.legal_core.models import Question, Status
from packages.legal_core.orchestrator import Orchestrator
from packages.legal_core.ports import ProviderUnavailable
from scripts.evaluate import evaluate, percentile


@pytest.mark.parametrize("hybrid", [False, True])
def test_retrieval_honors_large_limit(corpus, hybrid):
    base = corpus.versions[0]
    chunks = [
        base.chunks[0].model_copy(
            update={"chunk_id": uuid4(), "text": f"оплата {n}", "embedding": [1.0, 0.0]}
        )
        for n in range(45)
    ]
    changed = corpus.model_copy(
        update={
            "versions": [base.model_copy(update={"chunks": chunks})],
            "embedding_model": "BAAI/bge-m3" if hybrid else None,
        }
    )
    index = OfflineIndex(changed, embed_query=lambda query: [1.0, 0.0])
    assert len(index.search("нетсовпадений" if hybrid else "оплата", limit=40)) == 40
    assert index.search("оплата", limit=0) == []


def test_blank_quote_is_rejected(index):
    def forge(draft, evidence):
        claim = draft.claims[0]
        cite = claim.citations[0].model_copy(update={"quote": " "})
        return draft.model_copy(update={"claims": [claim.model_copy(update={"citations": [cite]})]})

    answer = Orchestrator(index, EvidenceLLM(transform=forge)).answer(Question(question="оплаты"))
    assert answer.status == Status.INSUFFICIENT_EVIDENCE
    assert not answer.citations


def cases(index):
    chunk = next(c for c in index.chunks if "10 рабочих" in c.text)
    return [
        {
            "id": "one",
            "category": "answerable",
            "request": {"question": "срок оплаты", "event_date": "2024-06-01"},
            "expected_status": ["ANSWERED"],
            "required_evidence_ids": [str(chunk.chunk_id)],
            "answerable": True,
            "banned_claims": [],
        }
    ]


def test_evaluation_metrics(index):
    report = evaluate(cases(index), index, EvidenceLLM())
    assert report["pass_rate"] == 1
    assert report["recall_at_k"] == 1
    assert report["false_refusal_rate"] == 0
    assert report["citation_validity_rate"] == report["status_accuracy"] == 1
    assert report["cases"][0]["citations_valid"]
    assert percentile([4, 1, 3, 2], 0.95) == 4


def test_no_match_has_zero_precision_and_recall(index):
    data = cases(index)
    data[0]["request"]["question"] = "zzzzzzzzzz"
    report = evaluate(data, index)
    assert report["precision_at_k"] == report["recall_at_k"] == 0
    assert report["pass_rate"] is None
    assert report["latency_ms"]["total_ms"]["p95"] is None


def test_unknown_evidence_fails_instead_of_misleading_score(index):
    data = cases(index)
    data[0]["required_evidence_ids"] = [str(uuid4())]
    with pytest.raises(ValueError, match="absent from index"):
        evaluate(data, index)


def test_banned_claim_and_missing_evidence_fail(index):
    data = cases(index)
    data[0]["banned_claims"] = ["10 рабочих"]
    assert evaluate(data, index, EvidenceLLM())["pass_rate"] == 0
    data[0]["banned_claims"] = []
    report = evaluate(data, index, EvidenceLLM(status=Status.INSUFFICIENT_EVIDENCE))
    assert report["pass_rate"] == 0
    assert report["false_refusal_rate"] == 1
    assert report["citation_validity_rate"] is None


def test_provider_errors_are_not_refusals(index):
    class BrokenLLM:
        def generate(self, request, evidence):
            raise ProviderUnavailable("unavailable")

    report = evaluate(cases(index), index, BrokenLLM())
    assert report["provider_errors"] == 1
    assert report["pass_rate"] == 0
    assert report["false_refusal_rate"] is None


def test_fixed_demo_suite_has_30_cases_and_valid_labels(index):
    data = [
        json.loads(line)
        for line in Path("data/eval/demo.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(data) == len({c["id"] for c in data}) == 30
    assert {c["category"] for c in data} == {
        "answerable",
        "multi_source_temporal",
        "insufficient",
        "false_premise_clarification",
        "adversarial",
    }
    report = evaluate(data, index)
    assert report["mode"] == "retrieval_only"
    assert report["case_count"] == 30
