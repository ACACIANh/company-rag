from core.llm.base import LLMClient
from app.graph.prompts import REWRITE_QUERY


def rewrite_query_node(state: dict, *, llm: LLMClient) -> dict:
    history = state.get("chat_history", [])
    history_text = "\n".join(
        f"{m['role']}: {m['content']}" for m in history
    ) if history else "없음"
    prompt = REWRITE_QUERY.format(question=state["question"], chat_history=history_text)
    rewritten = llm.complete(prompt).strip()
    return {"rewritten_question": rewritten}
