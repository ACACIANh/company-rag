from app.graph.tools.base import ToolHandler


class _DummyHandler:
    name = "echo"
    def plan(self, args):
        return (args["text"], "select")
    def execute(self, planned_action):
        return f"ran: {planned_action}"


def test_tool_handler_protocol_runtime_checkable():
    h = _DummyHandler()
    assert isinstance(h, ToolHandler)
    assert h.plan({"text": "hi"}) == ("hi", "select")
    assert h.execute("hi") == "ran: hi"
