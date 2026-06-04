from unittest.mock import MagicMock

from app.graph.tools.registry import build_tool_registry


def test_registry_includes_all_tools():
    reg = build_tool_registry(
        llm=MagicMock(), sql_pool=MagicMock(),
        fga_client=MagicMock(), app_pool=MagicMock(),
    )
    assert "query_business_data" in reg.handlers
    assert "manage_permission" in reg.handlers
    assert "query_audit_history" in reg.handlers
    names = {t.name for t in reg.tool_defs}
    assert names == {"query_business_data", "manage_permission", "query_audit_history"}
