from core.llm.base import LLMClient
from app.graph.prompts import ROUTER_PROMPT

_VALID_ROUTES = {"doc_search", "agent", "capability"}
_VALID_STRATEGIES = {"none", "contextual", "multi_query"}
_CLARIFY_THRESHOLD = 0.75


def router_node(state: dict, *, llm: LLMClient) -> dict:
    # 라우팅·도구입력은 원본 질문으로 — rewrite(문서검색 편향) 비결정성 차단 (ADR-0031)
    prompt = ROUTER_PROMPT.format(question=state["question"])
    response = llm.complete(prompt).strip().lower()

    parts = response.split(":")
    route_raw = parts[0].strip()
    strategy_raw = parts[1].strip() if len(parts) > 1 else "none"
    try:
        confidence = float(parts[2].strip()) if len(parts) > 2 else 1.0
    except ValueError:
        confidence = 1.0

    route = route_raw if route_raw in _VALID_ROUTES else "doc_search"
    strategy = strategy_raw if strategy_raw in _VALID_STRATEGIES else "none"

    if confidence < _CLARIFY_THRESHOLD and route in {"doc_search", "agent"}:
        return {
            "route": "clarify",
            "route_confidence": confidence,
            "rewrite_strategy": strategy,
            "tool_input": "",
        }

    tool_input = state["question"] if route == "agent" else ""
    return {
        "route": route,
        "route_confidence": confidence,
        "rewrite_strategy": strategy,
        "tool_input": tool_input,
    }
