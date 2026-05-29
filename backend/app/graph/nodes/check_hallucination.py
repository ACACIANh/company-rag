from core.llm.base import LLMClient
from app.graph.prompts import CHECK_HALLUCINATION


def check_hallucination_node(state: dict, *, llm: LLMClient) -> dict:
    if not state["documents"]:
        return {"hallucination_passed": True}
    context = "\n\n".join(d.chunk.text for d in state["documents"])
    prompt = CHECK_HALLUCINATION.format(context=context, answer=state["answer"])
    response = llm.complete(prompt).strip().upper()
    passed = "YES" in response
    if passed:
        return {"hallucination_passed": True}
    return {"hallucination_passed": False, "retry_count": state["retry_count"] + 1}
