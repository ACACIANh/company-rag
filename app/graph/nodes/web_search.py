from shared.retriever.base import Retriever


async def web_search_node(state: dict, *, retriever: Retriever) -> dict:
    query = state.get("rewritten_question") or state["question"]
    results = await retriever.retrieve(query, top_k=5)
    return {"documents": results}
