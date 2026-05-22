from shared.llm.base import LLMClient
from app.graph.prompts import REWRITE_QUERY


def rewrite_query_node(state: dict, *, llm: LLMClient) -> dict:
    prompt = REWRITE_QUERY.format(question=state["question"])
    rewritten = llm.complete(prompt).strip()
    return {"rewritten_question": rewritten}
