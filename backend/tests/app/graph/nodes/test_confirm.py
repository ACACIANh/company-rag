from unittest.mock import patch

from app.graph.nodes.confirm import confirm_node


def test_confirm_node_passes_when_reason_given():
    # ADR-0027: resume 값은 사유 문자열. 비어있지 않으면 통과.
    with patch("app.graph.nodes.confirm.interrupt", return_value="분기 급여 정산 검토 목적"):
        result = confirm_node({
            "tool_input": "전직원 급여 조회",
            "rewritten_question": "전직원 급여 보여줘",
        })

    assert result["confirmed"] is True
    assert result["justification"] == "분기 급여 정산 검토 목적"


def test_confirm_node_blocks_when_reason_empty():
    with patch("app.graph.nodes.confirm.interrupt", return_value="   "):
        result = confirm_node({
            "tool_input": "전직원 급여 조회",
            "rewritten_question": "전직원 급여 보여줘",
        })

    assert result["confirmed"] is False
    assert result["justification"] == ""


def test_confirm_node_blocks_when_cancelled():
    # 취소(None/비문자열)는 미기재로 간주 — 실행 안 함.
    with patch("app.graph.nodes.confirm.interrupt", return_value=None):
        result = confirm_node({
            "tool_input": "전직원 급여 조회",
            "rewritten_question": "전직원 급여 보여줘",
        })

    assert result["confirmed"] is False
    assert result["justification"] == ""


def test_confirm_node_calls_interrupt_with_tool_input():
    with patch("app.graph.nodes.confirm.interrupt", return_value="사유") as mock_interrupt:
        confirm_node({
            "tool_input": "인사 시스템 조회",
            "rewritten_question": "내 연차 잔여일 알려줘",
        })

    call_args = mock_interrupt.call_args[0][0]
    assert "인사 시스템 조회" in str(call_args)


def test_confirm_node_uses_rewritten_question_when_tool_input_empty():
    with patch("app.graph.nodes.confirm.interrupt", return_value="사유") as mock_interrupt:
        confirm_node({
            "tool_input": "",
            "rewritten_question": "캘린더 확인해줘",
        })

    call_args = mock_interrupt.call_args[0][0]
    assert "캘린더 확인해줘" in str(call_args)
