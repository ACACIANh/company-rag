from unittest.mock import patch

from app.graph.nodes.confirm import confirm_node


def test_confirm_node_returns_true_when_user_approves():
    with patch("app.graph.nodes.confirm.interrupt", return_value=True):
        result = confirm_node({
            "tool_input": "회의실 A 예약",
            "rewritten_question": "회의실 예약해줘",
        })

    assert result == {"confirmed": True}


def test_confirm_node_returns_false_when_user_denies():
    with patch("app.graph.nodes.confirm.interrupt", return_value=False):
        result = confirm_node({
            "tool_input": "슬랙 메시지 발송",
            "rewritten_question": "팀에 공지 보내줘",
        })

    assert result == {"confirmed": False}


def test_confirm_node_calls_interrupt_with_tool_input():
    with patch("app.graph.nodes.confirm.interrupt", return_value=True) as mock_interrupt:
        confirm_node({
            "tool_input": "인사 시스템 조회",
            "rewritten_question": "내 연차 잔여일 알려줘",
        })

    call_args = mock_interrupt.call_args[0][0]
    assert "인사 시스템 조회" in str(call_args)


def test_confirm_node_uses_rewritten_question_when_tool_input_empty():
    with patch("app.graph.nodes.confirm.interrupt", return_value=False) as mock_interrupt:
        confirm_node({
            "tool_input": "",
            "rewritten_question": "캘린더 확인해줘",
        })

    call_args = mock_interrupt.call_args[0][0]
    assert "캘린더 확인해줘" in str(call_args)
