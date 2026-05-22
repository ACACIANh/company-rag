from shared.retriever.base import Retriever


def web_search_node(state: dict, *, retriever: Retriever) -> dict:
    query = state.get("rewritten_question") or state["question"]
    results = retriever.retrieve(query, top_k=5)
    return {"documents": results}
