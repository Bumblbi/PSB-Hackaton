import hashlib
import json
import re
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from docx import Document
from pypdf import PdfReader

from packages.legal_core.models import Chunk, Corpus, DocumentVersion

MAX_FILE_BYTES = 20 * 1024 * 1024


def safe_file(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("source must be a file inside corpus root")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("source exceeds 20 MiB")
    return path


def extract(path: Path) -> list[tuple[int | None, str]]:
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return [(None, path.read_text(encoding="utf-8"))]
    if suffix == ".pdf":
        return [(i, page.extract_text() or "") for i, page in enumerate(PdfReader(path).pages, 1)]
    if suffix == ".docx":
        # OOXML zip expansion is bounded before python-docx opens it.
        from zipfile import ZipFile

        with ZipFile(path) as archive:
            if sum(x.file_size for x in archive.infolist()) > 50 * 1024 * 1024:
                raise ValueError("expanded DOCX exceeds 50 MiB")
        doc = Document(path)
        paragraphs = []
        for block in doc.iter_inner_content():
            if hasattr(block, "text"):
                paragraphs.append(block.text)
            else:
                for row in block.rows:
                    paragraphs.append(" | ".join(cell.text for cell in row.cells))
        return [(None, "\n".join(paragraphs))]
    raise ValueError("supported source types: TXT, PDF, DOCX")


def ingest_manifest(manifest_path: Path) -> Corpus:
    """Trusted operator manifest supplies dates/relationships; never infer legal validity."""
    root = manifest_path.resolve().parent
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    versions = []
    for entry in manifest["documents"]:
        path = safe_file(root, entry["path"])
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        doc_id = uuid5(NAMESPACE_URL, "psb:document:" + entry["key"])
        metadata = {
            key: entry.get(key)
            for key in (
                "revision",
                "title",
                "kind",
                "valid_from",
                "valid_to",
                "is_current_only",
                "amends_key",
            )
        }
        version_id = uuid5(
            doc_id, checksum + json.dumps(metadata, sort_keys=True, ensure_ascii=False)
        )
        chunks = []
        for page, text in extract(path):
            # Preserve paragraph/point boundaries and exact source substrings.
            locator = f"страница {page}" if page else "начало документа"
            for paragraph in re.split(r"\n\s*\n|\n(?=\s*(?:\d+[.)]|Статья|Раздел|Глава))", text):
                paragraph = paragraph.strip()
                if not paragraph:
                    continue
                heading = paragraph.splitlines()[0]
                if re.match(r"^(?:\d+[.)]|Статья|Раздел|Глава)", heading):
                    locator = heading[:200] + (f", страница {page}" if page else "")
                # Approximate 350–800 tokens, 400-character overlap for long sections.
                start = 0
                while start < len(paragraph):
                    end = min(start + 2800, len(paragraph))
                    if end < len(paragraph):
                        boundary = paragraph.rfind(" ", start + 2000, end)
                        if boundary > start:
                            end = boundary
                    part = paragraph[start:end]
                    ordinal = len(chunks)
                    chunk_locator = f"{locator}, фрагмент {ordinal + 1}"
                    chunks.append(
                        Chunk(
                            chunk_id=uuid5(version_id, f"{ordinal}:{part}"),
                            document_id=doc_id,
                            version_id=version_id,
                            ordinal=ordinal,
                            locator=chunk_locator,
                            text=part,
                            page=page,
                        )
                    )
                    if end == len(paragraph):
                        break
                    start = end - 400
        versions.append(
            DocumentVersion(
                document_id=doc_id,
                version_id=version_id,
                title=entry["title"],
                kind=entry["kind"],
                revision=entry["revision"],
                source_name=path.name,
                source_hash=checksum,
                valid_from=entry.get("valid_from"),
                valid_to=entry.get("valid_to"),
                is_current_only=entry.get("is_current_only", False),
                amends_document_id=uuid5(NAMESPACE_URL, "psb:document:" + entry["amends_key"])
                if entry.get("amends_key")
                else None,
                chunks=chunks,
            )
        )
    return Corpus(versions=versions)
