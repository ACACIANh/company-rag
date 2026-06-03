from unittest.mock import patch

from app.graph.nodes.confirm import confirm_node


def _pending():
    return [{
        "id": "c1", "name": "query_business_data", "args": {"question": "전직원 급여"},
        "planned_action": "SELECT salary FROM business.employees", "risk": "bulk_select",
        "decision": "JUSTIFY_AND_APPROVE",
    }]


def test_confirm_passes_when_reason_given():
    with patch("app.graph.nodes.confirm.interrupt", return_value="감사 목적"):
        out = confirm_node({"pending_tool_calls": _pending()})
    assert out["confirmed"] is True
    assert out["justification"] == "감사 목적"


def test_confirm_blocks_when_reason_empty():
    with patch("app.graph.nodes.confirm.interrupt", return_value="   "):
        out = confirm_node({"pending_tool_calls": _pending()})
    assert out["confirmed"] is False
    assert out["justification"] == ""


def test_confirm_blocks_when_cancelled():
    with patch("app.graph.nodes.confirm.interrupt", return_value=None):
        out = confirm_node({"pending_tool_calls": _pending()})
    assert out["confirmed"] is False
    assert out["justification"] == ""


def test_confirm_exposes_planned_action_in_interrupt():
    with patch("app.graph.nodes.confirm.interrupt", return_value="감사 목적") as mi:
        out = confirm_node({"pending_tool_calls": _pending()})
    payload = str(mi.call_args[0][0])
    assert "SELECT salary FROM business.employees" in payload
    assert out["confirmed"] is True and out["justification"] == "감사 목적"
