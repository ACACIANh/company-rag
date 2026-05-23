from shared.models import SearchResult
from shared.reranker.base import Reranker
from shared.reranker.noop_reranker import NoOpReranker
from shared.retriever.base import Retriever


def retrieve_node(
    state: dict,
    *,
    retriever: Retriever,
    reranker: Reranker | None = None,
    retrieve_top_k: int = 20,
    top_k: int = 5,
) -> dict:
    query = state.get("rewritten_question") or state["question"]
    allowed_doc_ids = state.get("allowed_doc_ids", [])
    results: list[SearchResult] = retriever.retrieve(
        query, top_k=retrieve_top_k, filter_doc_ids=allowed_doc_ids
    )
    _reranker = reranker or NoOpReranker()
    reranked = _reranker.rerank(query, results, top_k=top_k)
    return {"documents": reranked}
