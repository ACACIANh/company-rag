from shared.models import SearchResult
from shared.retriever.base import Retriever


def retrieve_node(state: dict, *, retriever: Retriever) -> dict:
    query = state.get("rewritten_question") or state["question"]
    results: list[SearchResult] = retriever.retrieve(query, top_k=5)
    return {"documents": results}
