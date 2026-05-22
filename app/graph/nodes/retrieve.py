from shared.models import SearchResult
from shared.retriever.base import Retriever


def retrieve_node(state: dict, *, retriever: Retriever) -> dict:
    results: list[SearchResult] = retriever.retrieve(state["question"], top_k=5)
    return {"documents": results}
