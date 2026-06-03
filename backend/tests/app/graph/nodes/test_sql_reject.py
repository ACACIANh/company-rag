from app.graph.nodes.sql_reject import sql_reject_node


def test_deny_produces_rejection_answer():
    result = sql_reject_node({"gate_decision": "DENY", "confirmed": False})
    assert result["answer"]
    assert "권한" in result["answer"] or "실행할 수 없" in result["answer"]
    assert result["citations"] == []


def test_cancel_produces_cancellation_answer():
    # 게이트는 통과(JUSTIFY_AND_APPROVE)했으나 사유 미기재로 취소
    result = sql_reject_node({"gate_decision": "JUSTIFY_AND_APPROVE", "confirmed": False})
    assert result["answer"]
    assert "취소" in result["answer"]
