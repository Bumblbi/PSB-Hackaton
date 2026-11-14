import argparse
import hashlib
import json
import math
from pathlib import Path
from time import perf_counter

from adapters.llm.gateway import SYSTEM, VERIFY, GroqProvider, OrganizerProvider
from adapters.search.offline_index import OfflineIndex
from apps.api.app.settings import Settings
from packages.legal_core.models import Question, Status
from packages.legal_core.orchestrator import Orchestrator
from packages.legal_core.ports import ProviderUnavailable


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)] if ordered else None


def evaluate(cases, index, llm=None, k=8):
    rows = []
    chunks = {str(c.chunk_id): c for c in index.chunks}
    for case in cases:
        request = Question.model_validate(case["request"])
        expected = {str(value) for value in case.get("required_evidence_ids", [])}
        unknown = expected - chunks.keys()
        if unknown:
            raise ValueError(f"{case['id']}: evidence IDs absent from index")
        query = " ".join(
            [m.content for m in request.history if m.role == "user"][-3:] + [request.question]
        )
        started = perf_counter()
        retrieved = index.search(query, limit=k)
        elapsed = (perf_counter() - started) * 1000
        found = {str(c.chunk_id) for c in retrieved}
        row = {
            "id": case["id"],
            "category": case["category"],
            "retrieval_ms": round(elapsed, 3),
            "precision_at_k": (
                (len(found & expected) / len(found) if found else 0) if expected else None
            ),
            "recall_at_k": len(found & expected) / len(expected) if expected else None,
        }
        if llm is not None:
            try:
                answer = Orchestrator(index, llm).answer(request)
            except ProviderUnavailable:
                row.update(error="provider_unavailable", passed=False)
                rows.append(row)
                continue
            valid = all(
                str(c.chunk_id) in chunks
                and c.quote.strip()
                and c.quote in chunks[str(c.chunk_id)].text
                and c.document_id == chunks[str(c.chunk_id)].document_id
                and c.version_id == chunks[str(c.chunk_id)].version_id
                and c.locator == chunks[str(c.chunk_id)].locator
                for c in answer.citations
            )
            cited = {str(c.chunk_id) for c in answer.citations}
            banned = any(
                text.casefold() in answer.answer.casefold()
                for text in case.get("banned_claims", [])
            )
            status_ok = answer.status.value in case["expected_status"]
            row.update(
                status=answer.status.value,
                status_correct=status_ok,
                citations_valid=bool(valid),
                citation_validity=bool(valid) if answer.citations else None,
                citation_count=len(answer.citations),
                evidence_complete=expected <= cited,
                banned_claim_found=banned,
                false_refusal=case["answerable"]
                and answer.status not in {Status.ANSWERED, Status.PARTIAL, Status.FALSE_PREMISE},
                total_ms=answer.timings_ms["total"],
                passed=status_ok and bool(valid) and expected <= cited and not banned,
            )
        rows.append(row)

    def average(key):
        values = [r[key] for r in rows if r.get(key) is not None]
        return sum(values) / len(values) if values else None

    return {
        "index_version": index.index_version,
        "mode": "answers" if llm is not None else "retrieval_only",
        "k": k,
        "case_count": len(rows),
        "precision_at_k": average("precision_at_k"),
        "recall_at_k": average("recall_at_k"),
        "pass_rate": average("passed"),
        "status_accuracy": average("status_correct"),
        "citation_validity_rate": average("citation_validity"),
        "false_refusal_rate": (
            sum(r.get("false_refusal", False) for r in rows) / sum(c["answerable"] for c in cases)
            if llm is not None
            and sum(c["answerable"] for c in cases)
            and not any("error" in r for r in rows)
            else None
        ),
        "provider_errors": sum("error" in r for r in rows),
        "latency_ms": {
            key: {
                "p50": percentile([r[key] for r in rows if key in r], 0.5),
                "p95": percentile([r[key] for r in rows if key in r], 0.95),
            }
            for key in ("retrieval_ms", "total_ms")
        },
        "cases": rows,
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate fixed closed-corpus cases")
    parser.add_argument("index", type=Path)
    parser.add_argument("cases", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--answers", action="store_true")
    parser.add_argument("--k", type=int, default=8)
    args = parser.parse_args()
    if args.k < 1:
        parser.error("k must be positive")
    index = OfflineIndex.load(args.index)
    cases = [json.loads(line) for line in args.cases.read_text(encoding="utf-8").splitlines()]
    if not cases or len({c["id"] for c in cases}) != len(cases):
        parser.error("cases must have unique IDs and be nonempty")
    llm = None
    settings = Settings()
    if args.answers:
        if settings.llm_provider == "groq":
            llm = GroqProvider(
                api_key=settings.groq_api_key.get_secret_value(),
                model=settings.llm_model,
                corpus=index.corpus,
                timeout=settings.llm_timeout,
            )
        elif settings.llm_provider == "organizer":
            llm = OrganizerProvider(
                base_url=settings.organizer_base_url,
                api_key=settings.organizer_api_key.get_secret_value(),
                model=settings.llm_model,
                corpus=index.corpus,
                timeout=settings.llm_timeout,
            )
        else:
            parser.error("--answers requires configured LLM_PROVIDER")
    report = evaluate(cases, index, llm, args.k)
    report["model"] = settings.llm_model if args.answers else None
    report["provider"] = settings.llm_provider if args.answers else None
    report["cases_sha256"] = hashlib.sha256(args.cases.read_bytes()).hexdigest()
    report["prompts_sha256"] = hashlib.sha256((SYSTEM + VERIFY).encode()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"cases={len(cases)} mode={report['mode']} report={args.output}")
    return int(args.answers and any(not r["passed"] for r in report["cases"]))


if __name__ == "__main__":
    raise SystemExit(main())
