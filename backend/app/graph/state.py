from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from core.models import SearchResult, SourceRef


class PendingToolCall(TypedDict):
    id: str               # tool_call_id
    name: str             # 도구명
    args: dict            # 도구 인자
    planned_action: str   # 구체화된 동작(SQL의 경우 생성된 SQL)
    risk: str             # core.sql.risk 등급
    decision: str         # ALLOW / DENY / JUSTIFY_AND_APPROVE


class AgentState(TypedDict):
    question: str
    rewritten_question: str
    chat_history: list[dict]
    route: Literal["doc_search", "agent"]
    rewrite_strategy: Literal["none", "contextual", "multi_query"] | None
    multi_queries: list[str]
    documents: list[SearchResult]
    relevance_score: float
    retry_count: int
    answer: str
    citations: list[SourceRef]
    hallucination_passed: bool
    confirmed: bool
    tool_input: str
    user_id: str
    allowed_folders: list[str]   # permission_node가 채움 — 추려진 상위 폴더 목록
    generated_sql: str           # SQL 생성 노드가 채움 (ADR-0016)
    sql_risk: str                # 위험도 분류 노드가 채움 (ADR-0017)
    gate_decision: str           # 신원×위험도 게이트 결정 ALLOW/DENY/JUSTIFY_AND_APPROVE (ADR-0016, 0027)
    justification: str           # JUSTIFY_AND_APPROVE 경로에서 본인이 기재한 실행 사유 (ADR-0027)
    agent_messages: Annotated[list[AnyMessage], add_messages]  # 에이전트 도구 대화 (ADR-0023)
    pending_tool_calls: list[PendingToolCall]                   # interrupt를 넘는 in-flight 호출 (ADR-0023)
