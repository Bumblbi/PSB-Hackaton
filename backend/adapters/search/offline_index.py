import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path

from packages.legal_core.models import Chunk, Corpus
from packages.legal_core.ports import ProviderUnavailable


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-zа-яё0-9]+", text.lower().replace("ё", "е"))


class OfflineIndex:
    """BM25 fallback; optional BGE-M3 vectors use cosine similarity and RRF."""

    def __init__(self, corpus: Corpus, embed_query=None):
        self.corpus, self.embed_query = corpus, embed_query
        self.chunks = [c for v in corpus.versions for c in v.chunks]
        titles = {v.version_id: v.title for v in corpus.versions}
        self.terms = [Counter(tokens(titles[c.version_id] + " " + c.text)) for c in self.chunks]
        self.df = Counter(term for counts in self.terms for term in counts)
        self.avg_length = sum(sum(t.values()) for t in self.terms) / max(1, len(self.terms))
        self.index_version = hashlib.sha256(corpus.model_dump_json().encode()).hexdigest()

    @classmethod
    def load(cls, path: Path):
        # Missing or corrupt indexes are startup errors, not silently empty collections.
        return cls(Corpus.model_validate_json(path.read_text(encoding="utf-8")))

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        content = self.corpus.model_dump_json(indent=2)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)

    def search(self, query: str, limit: int = 20) -> list[Chunk]:
        if limit <= 0:
            return []
        query_terms = set(tokens(query))
        scores = []
        count = len(self.chunks)
        for i, terms in enumerate(self.terms):
            length = sum(terms.values())
            score = 0.0
            for term in query_terms:
                tf = terms[term]
                if tf:
                    idf = math.log(1 + (count - self.df[term] + 0.5) / (self.df[term] + 0.5))
                    score += (
                        idf
                        * tf
                        * 2.5
                        / (tf + 1.5 * (0.25 + 0.75 * length / max(self.avg_length, 1)))
                    )
            if score > 0:
                scores.append((i, score))
        candidate_limit = max(20, limit)
        ranked = sorted(scores, key=lambda row: (-row[1], row[0]))[:candidate_limit]
        fused = {i: 1 / (60 + rank) for rank, (i, _) in enumerate(ranked, 1)}
        if self.embed_query and self.corpus.embedding_model:
            try:
                vector = self.embed_query(query)
            except ProviderUnavailable:
                return [self.chunks[i] for i in sorted(fused, key=lambda i: (-fused[i], i))[:limit]]
            norm = math.sqrt(sum(x * x for x in vector))
            vector_scores = []
            for i, c in enumerate(self.chunks):
                if c.embedding and len(c.embedding) == len(vector):
                    other_norm = math.sqrt(sum(x * x for x in c.embedding))
                    score = sum(a * b for a, b in zip(vector, c.embedding)) / max(
                        norm * other_norm, 1e-12
                    )
                    vector_scores.append((i, score))
            for rank, (i, _) in enumerate(
                sorted(vector_scores, key=lambda x: -x[1])[:candidate_limit], 1
            ):
                fused[i] = fused.get(i, 0) + 1 / (60 + rank)
        return [self.chunks[i] for i in sorted(fused, key=lambda i: (-fused[i], i))[:limit]]


def read_corpus(path: Path) -> Corpus:
    return Corpus.model_validate(json.loads(path.read_text(encoding="utf-8")))
