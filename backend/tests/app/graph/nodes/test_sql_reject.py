from app.graph.nodes.sql_reject import sql_reject_node


def test_deny_produces_rejection_answer():
    result = sql_reject_node({"gate_decision": "DENY", "confirmed": False})
    assert result["answer"]
    assert "권한" in result["answer"] or "실행할 수 없" in result["answer"]
    assert result["citations"] == []


def test_cancel_produces_cancellation_answer():
    # 게이트는 통과(NEEDS_APPROVAL)했으나 사용자가 승인 거부
    result = sql_reject_node({"gate_decision": "NEEDS_APPROVAL", "confirmed": False})
    assert result["answer"]
    assert "취소" in result["answer"]
