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
다음 질문이 아래 중 하나에 해당하면 "rag"를, 그 외 일반 인사/상식 질문이면 "direct"를 한 단어로만 답하세요.

RAG가 필요한 질문 유형:
- 연차, 휴가, 출결, 근무 관련
- 복리후생, 급여, 경비 처리
- 코드 리뷰, 배포, 보안 정책
- 온보딩, 팀 구조, 도구/접근 권한
- 회의 문화, 성과 리뷰, 인시던트 대응
- 기타 회사 내부 규정이나 가이드라인

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
