from datetime import date

from conftest import EvidenceLLM

from adapters.search.offline_index import OfflineIndex
from packages.legal_core.models import Corpus, Question, Status
from packages.legal_core.orchestrator import Orchestrator
from packages.legal_core.ports import ProviderUnavailable


def test_current_law_can_answer_inside_confirmed_interval(corpus):
    law = corpus.versions[0].model_copy(update={"kind": "law", "is_current_only": True})
    index = OfflineIndex(Corpus(versions=[law]))
    answer = Orchestrator(index, EvidenceLLM()).answer(
        Question(question="срок оплаты", event_date=date(2024, 1, 1))
    )
    assert answer.status == Status.ANSWERED


def test_embedding_unavailable_falls_back_to_bm25(corpus):
    def unavailable(query):
        raise ProviderUnavailable("unavailable")

    index = OfflineIndex(
        corpus.model_copy(update={"embedding_model": "BAAI/bge-m3"}), embed_query=unavailable
    )
    assert index.search("оплаты")
