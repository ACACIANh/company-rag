from shared.models import Chunk, SearchResult

_MOCK_DISPATCH = {
    "캘린더": "캘린더 Mock: 다음 주 월요일 오전 10시 회의 일정이 있습니다.",
    "회의실": "회의실 Mock: 회의실 A가 2026-06-02 14:00에 예약됐습니다.",
    "연차": "인사 시스템 Mock: 연차 잔여일은 10일입니다.",
    "공지": "알림 Mock: 팀 전체에 공지가 발송됐습니다.",
}


def tool_executor_node(state: dict) -> dict:
    action = state.get("tool_input") or state["rewritten_question"]
    mock_text = next(
        (v for k, v in _MOCK_DISPATCH.items() if k in action),
        f"Mock 도구 실행 완료: '{action}'",
    )
    result = SearchResult(
        chunk=Chunk(text=mock_text, source="mock-tool", chunk_id="mock-0"),
        score=1.0,
    )
    return {"documents": [result]}
