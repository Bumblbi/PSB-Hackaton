"""Provisional JSONL runner. Organizer signature/transport must be confirmed separately.

Input: Question JSON object, one independent case per line. Output: Answer JSON.
No DB, Redis, API server or global conversation state. No synthetic model fallback.
"""

import json
import os
import sys
from pathlib import Path

from pydantic import ValidationError

from adapters.llm.gateway import OrganizerProvider
from adapters.search.offline_index import OfflineIndex
from packages.legal_core.models import Question
from packages.legal_core.orchestrator import Orchestrator
from packages.legal_core.ports import ProviderUnavailable


def solve(payload: dict, *, index=None, llm=None) -> dict:
    request = Question.model_validate(payload)
    index = index or OfflineIndex.load(
        Path(os.environ.get("INDEX_PATH", "submission/index/corpus.json"))
    )
    llm = llm or OrganizerProvider(
        base_url=os.environ.get("ORGANIZER_BASE_URL", ""),
        api_key=os.environ.get("ORGANIZER_API_KEY", ""),
        model=os.environ.get("LLM_MODEL", ""),
        corpus=index.corpus,
    )
    return Orchestrator(index, llm).answer(request).model_dump(mode="json")


def main():
    failed = False
    for line in sys.stdin:
        try:
            if len(line) > 256000:
                raise ValueError("input too large")
            result = solve(json.loads(line))
        except (ValueError, ValidationError, OSError, ProviderUnavailable):
            # Never turn infrastructure failure into an apparent evaluated legal answer.
            result = {"error": "Invalid input, missing index, or unavailable organizer provider"}
            failed = True
        print(json.dumps(result, ensure_ascii=False), flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
