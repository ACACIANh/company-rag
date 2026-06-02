from typing import Literal, TypedDict

from core.models import SearchResult, SourceRef


class AgentState(TypedDict):
    question: str
    rewritten_question: str
    chat_history: list[dict]
    route: Literal["doc_search", "tool_call"]
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
    gate_decision: str           # 신원×위험도 게이트 결정 ALLOW/DENY/NEEDS_APPROVAL (ADR-0016)
