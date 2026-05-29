from shared.llm.base import LLMClient
from app.graph.prompts import MULTI_QUERY_PROMPT


def multi_query_node(state: dict, *, llm: LLMClient) -> dict:
    question = state.get("rewritten_question") or state.get("question", "")
    prompt = MULTI_QUERY_PROMPT.format(question=question)
    response = llm.complete(prompt).strip()

    queries = [q.strip() for q in response.splitlines() if q.strip()]
    if not queries:
        queries = [question]

    return {"multi_queries": queries[:3]}
