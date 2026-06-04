import pytest

from app.graph.tools.base import ToolAgent


class _DummyAgent:
    name = "echo"
    def plan(self, args):
        return (args["text"], "select")
    async def execute(self, planned_action, risk=""):
        return f"ran: {planned_action}"


@pytest.mark.asyncio
async def test_tool_agent_protocol_runtime_checkable():
    h = _DummyAgent()
    assert isinstance(h, ToolAgent)
    assert h.plan({"text": "hi"}) == ("hi", "select")
    assert await h.execute("hi", "select") == "ran: hi"
