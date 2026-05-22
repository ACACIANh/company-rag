from shared.llm.base import LLMClient
from app.graph.prompts import ROUTER_PROMPT

_VALID_ROUTES = {"doc_search", "web_search", "tool_call"}


def router_node(state: dict, *, llm: LLMClient) -> dict:
    prompt = ROUTER_PROMPT.format(question=state["rewritten_question"])
    response = llm.complete(prompt).strip().lower()

    route = response if response in _VALID_ROUTES else "doc_search"
    tool_input = state["rewritten_question"] if route == "tool_call" else ""
    return {"route": route, "tool_input": tool_input}
