import pytest

from app.graph.tools.base import ToolHandler


class _DummyHandler:
    name = "echo"
    def plan(self, args):
        return (args["text"], "select")
    async def execute(self, planned_action):
        return f"ran: {planned_action}"


@pytest.mark.asyncio
async def test_tool_handler_protocol_runtime_checkable():
    h = _DummyHandler()
    assert isinstance(h, ToolHandler)
    assert h.plan({"text": "hi"}) == ("hi", "select")
    assert await h.execute("hi") == "ran: hi"
