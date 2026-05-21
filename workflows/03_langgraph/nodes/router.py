from typing import TypedDict
from shared.llm.base import LLMClient


class GraphState(TypedDict):
    question: str
    route: str
    context: list
    answer: str
    sources: list[str]
    trace: list[dict]


_ROUTER_PROMPT = """\
다음 질문이 회사 내부 문서(정책, 규정, 가이드라인 등)와 관련 있으면 "rag"를,
일반적인 인사나 상식 질문이면 "direct"를 한 단어로만 답하세요.

질문: {question}
분류:"""


def make_router_node(llm: LLMClient):
    def router_node(state: GraphState) -> GraphState:
        response = llm.complete(_ROUTER_PROMPT.format(question=state["question"]))
        route = "rag" if "rag" in response.lower() else "direct"
        return {
            **state,
            "route": route,
            "trace": state.get("trace", []) + [{"node": "router", "route": route}],
        }
    return router_node
