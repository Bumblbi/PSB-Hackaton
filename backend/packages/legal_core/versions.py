from datetime import date
from uuid import UUID

from .models import Chunk, Corpus, Question, Status


def resolve_versions(
    corpus: Corpus,
    candidates: list[Chunk],
    request: Question,
) -> tuple[list[Chunk], Status | None, str]:
    """Half-open validity intervals; unknown/overlapping intervals never imply validity."""
    at = request.event_date or date.today()
    ids = {request.document_id} if request.document_id else {c.document_id for c in candidates}
    selected = [v for v in corpus.versions if v.document_id in ids]
    if request.document_kind:
        selected = [v for v in selected if v.kind == request.document_kind]
    ids = {v.document_id for v in selected}
    seen_versions = {v.version_id for v in selected}
    selected += [
        v
        for v in corpus.versions
        if v.amends_document_id in ids and v.version_id not in seen_versions
    ]
    groups: dict[UUID, list] = {}
    for v in selected:
        groups.setdefault(v.document_id, []).append(v)
    allowed = set()
    for versions in groups.values():
        historical = request.event_date and request.event_date < date.today()
        active = [
            v
            for v in versions
            if v.valid_from and v.valid_from <= at and (v.valid_to is None or at < v.valid_to)
        ]
        if historical and versions[0].kind == "law" and not active:
            return (
                [],
                Status.HISTORICAL_LAW_UNAVAILABLE,
                ("В корпусе нет подтверждённой редакции закона на дату события."),
            )
        if not active:
            # Future/expired amendments do not prevent use of the base document.
            if versions[0].kind == "amendment" and all(v.valid_from for v in versions):
                continue
            return (
                [],
                Status.NEED_CLARIFICATION,
                ("Уточните редакцию документа: период действия на указанную дату не подтверждён."),
            )
        if len(active) != 1:
            return (
                [],
                Status.NEED_CLARIFICATION,
                ("В корпусе пересекаются интервалы редакций. Уточните применимую редакцию."),
            )
        allowed.add(active[0].version_id)
    # Include amendments even when their vocabulary differs from the base text.
    result = [c for c in candidates if c.version_id in allowed]
    seen = {c.chunk_id for c in result}
    for v in selected:
        if v.version_id in allowed:
            for c in v.chunks:
                if c.chunk_id not in seen:
                    result.append(c)
                    seen.add(c.chunk_id)
    return result, None, ""
