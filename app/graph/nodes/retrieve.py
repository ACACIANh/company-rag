from shared.models import SearchResult
from shared.retriever.base import Retriever


def retrieve_node(state: dict, *, retriever: Retriever) -> dict:
    query = state.get("rewritten_question") or state["question"]
    allowed_doc_ids = state.get("allowed_doc_ids", [])
    results: list[SearchResult] = retriever.retrieve(
        query, top_k=5, filter_doc_ids=allowed_doc_ids
    )
    return {"documents": results}
