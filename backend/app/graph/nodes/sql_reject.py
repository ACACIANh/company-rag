"""SQL 거부/취소 응답 노드 (ADR-0016).

게이트 DENY 또는 사용자의 승인 거부(NEEDS_APPROVAL 취소) 시, 실행 없이 사유를
담은 답을 직접 만든다. RAG generate/hallucination 경로를 거치지 않고 save_memory로
바로 이어진다 — 거부는 문서 기반 생성이 아니라 정책 결과의 통보이기 때문이다.
"""
from core.sql.gate import DECISION_DENY

_DENY_MESSAGE = (
    "요청하신 작업은 현재 권한으로 실행할 수 없습니다. "
    "읽기 전용 조회는 가능하며, 변경·대량/민감 조회는 상위 권한자의 승인이 필요합니다."
)
_CANCEL_MESSAGE = "SQL 실행 요청이 취소되었습니다."


def sql_reject_node(state: dict) -> dict:
    if state.get("gate_decision") == DECISION_DENY:
        answer = _DENY_MESSAGE
    else:
        answer = _CANCEL_MESSAGE
    return {"answer": answer, "citations": []}
