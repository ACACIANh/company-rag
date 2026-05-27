from typing import Literal, TypedDict

from shared.models import SearchResult, SourceRef


class AgentState(TypedDict):
    question: str
    rewritten_question: str
    chat_history: list[dict]
    route: Literal["doc_search", "tool_call", "web_search"]
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
    allowed_doc_ids: list[str]   # deprecated — FGA 미연동 테스트 stub용
    user_teams: list[str]        # permission_node가 채움
    personal_doc_ids: list[str]  # permission_node가 채움
