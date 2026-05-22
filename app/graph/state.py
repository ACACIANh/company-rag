from typing import Literal, TypedDict

from shared.models import SearchResult


class AgentState(TypedDict):
    question: str
    rewritten_question: str
    chat_history: list[dict]
    route: Literal["doc_search", "tool_call", "web_search"]
    documents: list[SearchResult]
    relevance_score: float
    retry_count: int
    answer: str
    citations: list[str]
    hallucination_passed: bool
    confirmed: bool
    tool_input: str
    user_id: str           # 추가
    allowed_doc_ids: list[str]  # 추가 — 빈 리스트 = 전체 허용
