import json
from pathlib import Path

import pytest
from docx import Document

from adapters.ingest import extract, ingest_manifest, safe_file
from adapters.search.offline_index import OfflineIndex


def test_reproducible_index(corpus, tmp_path):
    again = ingest_manifest(Path("data/demo/manifest.json"))
    assert corpus == again
    first = OfflineIndex(corpus)
    path = tmp_path / "corpus.json"
    first.save(path)
    assert OfflineIndex.load(path).index_version == first.index_version


def test_metadata_changes_version_id(tmp_path):
    (tmp_path / "a.txt").write_text("1. Условие договора.", encoding="utf-8")
    entry = {
        "key": "a",
        "revision": "1",
        "title": "Договор",
        "kind": "contract",
        "path": "a.txt",
        "valid_from": "2020-01-01",
    }
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"documents": [entry]}), encoding="utf-8")
    first = ingest_manifest(manifest).versions[0]
    entry["valid_to"] = "2025-01-01"
    manifest.write_text(json.dumps({"documents": [entry]}), encoding="utf-8")
    second = ingest_manifest(manifest).versions[0]
    assert first.document_id == second.document_id
    assert first.version_id != second.version_id


def test_path_traversal(tmp_path):
    with pytest.raises(ValueError):
        safe_file(tmp_path, "../outside.txt")


def test_docx_tables_and_paragraphs(tmp_path):
    doc = Document()
    doc.add_paragraph("1. Условие договора")
    table = doc.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Срок оплаты"
    table.cell(0, 1).text = "10 дней"
    path = tmp_path / "source.docx"
    doc.save(path)
    result = extract(path)[0][1]
    assert "Условие договора" in result and "10 дней" in result


def test_unsupported_format(tmp_path):
    with pytest.raises(ValueError):
        extract(tmp_path / "source.exe")


def test_bm25_not_arbitrary(corpus):
    index = OfflineIndex(corpus)
    assert not index.search("abcdefghijk")
    assert index.search("оплаты")


def test_hybrid_vector_path(corpus):
    versions = []
    for v in corpus.versions:
        versions.append(
            v.model_copy(
                update={
                    "chunks": [c.model_copy(update={"embedding": [1.0, 0.0]}) for c in v.chunks]
                }
            )
        )
    vector_corpus = corpus.model_copy(
        update={"versions": versions, "embedding_model": "BAAI/bge-m3"}
    )
    index = OfflineIndex(vector_corpus, embed_query=lambda q: [1.0, 0.0])
    assert index.search("no lexical match")
