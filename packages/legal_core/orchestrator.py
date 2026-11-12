import re
from datetime import date
from time import perf_counter

from .models import Answer, Citation, Question, Status
from .ports import LLMGateway, SearchIndex
from .versions import resolve_versions

REFUSALS = {
    Status.INSUFFICIENT_EVIDENCE: "В предоставленном корпусе недостаточно подтверждений.",
    Status.OUT_OF_SCOPE: "Ассистент отвечает на юридические вопросы по предоставленному корпусу.",
    Status.DISALLOWED: "Не могу помочь с противоправными действиями.",
    Status.NEED_CLARIFICATION: "Уточните документ и дату события.",
    Status.HISTORICAL_LAW_UNAVAILABLE: "В корпусе нет нужной исторической редакции закона.",
}


class Orchestrator:
    def __init__(self, index: SearchIndex, llm: LLMGateway):
        self.index, self.llm = index, llm

    def answer(self, request: Question) -> Answer:
        started = perf_counter()
        timings = {}

        def finish(status, text, **kwargs):
            timings["total"] = round((perf_counter() - started) * 1000, 3)
            return Answer(status=status, answer=text, timings_ms=timings, **kwargs)

        # Dates inside the current turn are explicit evidence, not model-inferred metadata.
        if request.event_date is None:
            dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", request.question)
            if len(set(dates)) == 1:
                try:
                    request = request.model_copy(
                        update={"event_date": date.fromisoformat(dates[0])}
                    )
                except ValueError:
                    return finish(
                        Status.NEED_CLARIFICATION,
                        "Уточните корректную дату события.",
                        clarifying_question="На какую дату требуется ответ?",
                    )
            elif len(set(dates)) > 1:
                return finish(
                    Status.NEED_CLARIFICATION,
                    "Укажите дату события отдельным полем.",
                    clarifying_question="На какую из указанных дат требуется ответ?",
                )
        query = " ".join(
            [m.content for m in request.history if m.role == "user"][-3:] + [request.question]
        )
        retrieved = self.index.search(query, limit=40)
        if request.document_id:
            retrieved = [c for c in retrieved if c.document_id == request.document_id]
        evidence, blocked, reason = resolve_versions(self.index.corpus, retrieved, request)
        timings["retrieval"] = round((perf_counter() - started) * 1000, 3)
        if blocked:
            return finish(
                blocked,
                reason,
                reason=reason,
                missing_info=[reason],
                clarifying_question=reason if blocked == Status.NEED_CLARIFICATION else None,
            )
        # Gateway still classifies out-of-scope/disallowed requests when retrieval is empty.
        # Never silently truncate an applicable amendment or omit an entire source.
        amendment_versions = {
            v.version_id for v in self.index.corpus.versions if v.kind == "amendment"
        }
        selected = [c for c in evidence if c.version_id in amendment_versions]
        represented = {c.version_id for c in selected}
        for chunk in evidence:
            if chunk.version_id not in represented:
                selected.append(chunk)
                represented.add(chunk.version_id)
        if len(selected) > 8:
            return finish(
                Status.NEED_CLARIFICATION,
                "Для проверки нужно слишком много фрагментов. Сузьте документ или вопрос.",
                clarifying_question="Какой конкретно пункт или договор нужно проверить?",
                missing_info=["Требуется более узкий предмет запроса."],
            )
        selected_ids = {c.chunk_id for c in selected}
        evidence = (
            selected + [c for c in evidence if c.chunk_id not in selected_ids][: 8 - len(selected)]
        )
        draft = self.llm.generate(request, evidence)
        if draft.status in REFUSALS:
            return finish(
                draft.status,
                REFUSALS[draft.status],
                reason=draft.reason,
                missing_info=draft.missing_info or [REFUSALS[draft.status]],
                clarifying_question=(draft.clarifying_question or REFUSALS[draft.status])
                if draft.status == Status.NEED_CLARIFICATION
                else None,
            )
        if not draft.claims:
            return finish(
                Status.INSUFFICIENT_EVIDENCE,
                REFUSALS[Status.INSUFFICIENT_EVIDENCE],
                missing_info=["Нужны фрагменты, подтверждающие ответ."],
            )
        by_id = {c.chunk_id: c for c in evidence}
        # Do not send invalid drafts to a semantic checker or expose their text to a client.
        for claim in draft.claims:
            for cite in claim.citations:
                chunk = by_id.get(cite.chunk_id)
                if chunk is None or cite.quote not in chunk.text:
                    return finish(
                        Status.INSUFFICIENT_EVIDENCE,
                        "Проверка цитат не пройдена. Ответ не подтверждён корпусом.",
                        missing_info=["Нужны существующие дословные цитаты из выбранных редакций."],
                    )
        supported = self.llm.verify(draft.claims, evidence)
        if len(supported) != len(draft.claims) or not all(supported):
            return finish(
                Status.INSUFFICIENT_EVIDENCE,
                "Не удалось подтвердить все утверждения по указанным цитатам.",
                missing_info=["Нужны подтверждения каждого вывода."],
            )
        citations, paragraphs = [], []
        for claim in draft.claims:
            refs = []
            for cite in claim.citations:
                c = by_id[cite.chunk_id]
                ref = len(citations) + 1
                citations.append(
                    Citation(
                        ref=ref,
                        document_id=c.document_id,
                        version_id=c.version_id,
                        chunk_id=c.chunk_id,
                        locator=c.locator,
                        quote=cite.quote,
                    )
                )
                refs.append(f"[{ref}]")
            paragraphs.append(claim.text + " " + " ".join(refs))
        status = draft.status
        if status == Status.IGNORE_INJECTION:
            status = Status.ANSWERED
        if draft.missing_info and status == Status.ANSWERED:
            status = Status.PARTIAL
        return finish(
            status,
            "\n\n".join(paragraphs),
            citations=citations,
            reason=draft.reason,
            missing_info=draft.missing_info,
        )
