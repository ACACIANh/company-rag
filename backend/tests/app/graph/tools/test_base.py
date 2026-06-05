import dataclasses
import pytest

from app.graph.tools.base import ToolAgent, ToolResult


class _DummyAgent:
    name = "echo"
    label = "echo"
    def plan(self, args):
        return (args["text"], "select")
    async def execute(self, planned_action, risk=""):
        return ToolResult(text=f"ran: {planned_action}", summary="ran")


def test_tool_result_holds_text_and_summary():
    r = ToolResult(text="전체 표", summary="12행 조회")
    assert r.text == "전체 표"
    assert r.summary == "12행 조회"


def test_tool_result_is_frozen():
    r = ToolResult(text="a", summary="b")
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.text = "c"  # type: ignore[misc]


@pytest.mark.asyncio
async def test_tool_agent_protocol_runtime_checkable():
    h = _DummyAgent()
    assert isinstance(h, ToolAgent)
    assert h.plan({"text": "hi"}) == ("hi", "select")
    result = await h.execute("hi", "select")
    assert result.text == "ran: hi"
