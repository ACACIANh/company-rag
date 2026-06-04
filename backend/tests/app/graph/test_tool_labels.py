from langchain_core.messages import AIMessage

from app.graph.tool_labels import collect_tool_labels


def test_doc_search_route_returns_rag():
    assert collect_tool_labels("doc_search", []) == ["rag"]


def test_capability_route_returns_empty():
    assert collect_tool_labels("capability", []) == []


def test_agent_route_maps_tool_calls_to_labels():
    msgs = [
        AIMessage(content="", tool_calls=[
            {"name": "query_business_data", "args": {}, "id": "1"},
        ]),
        AIMessage(content="", tool_calls=[
            {"name": "query_audit_history", "args": {}, "id": "2"},
        ]),
    ]
    assert collect_tool_labels("agent", msgs) == ["sql", "audit"]


def test_agent_route_dedupes_preserving_order():
    msgs = [
        AIMessage(content="", tool_calls=[
            {"name": "query_audit_history", "args": {}, "id": "1"},
            {"name": "query_business_data", "args": {}, "id": "2"},
        ]),
        AIMessage(content="", tool_calls=[
            {"name": "query_audit_history", "args": {}, "id": "3"},
        ]),
    ]
    assert collect_tool_labels("agent", msgs) == ["audit", "sql"]


def test_agent_route_ignores_unknown_tool_names():
    msgs = [AIMessage(content="", tool_calls=[{"name": "ghost", "args": {}, "id": "1"}])]
    assert collect_tool_labels("agent", msgs) == []


def test_non_aimessage_entries_are_skipped():
    from langchain_core.messages import HumanMessage
    msgs = [HumanMessage(content="hi")]
    assert collect_tool_labels("agent", msgs) == []
