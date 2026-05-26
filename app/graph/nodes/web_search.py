from shared.retriever.base import Retriever


async def web_search_node(state: dict, *, retriever: Retriever | None) -> dict:
    if retriever is None:
        return {"documents": []}
    query = state.get("rewritten_question") or state["question"]
    results = await retriever.retrieve(query, top_k=5)
    return {"documents": results}
