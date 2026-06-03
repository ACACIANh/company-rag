from unittest.mock import MagicMock

from app.graph.tools.registry import build_tool_registry


def test_registry_contains_sql_tool():
    reg = build_tool_registry(llm=MagicMock(), sql_pool=MagicMock())
    assert "query_business_data" in reg.handlers
    assert reg.handlers["query_business_data"].name == "query_business_data"
    names = [t.name for t in reg.tool_defs]
    assert "query_business_data" in names
