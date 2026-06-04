from unittest.mock import MagicMock

from app.graph.tools.registry import build_tool_registry, tool_label_map


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


def test_tool_label_map_covers_all_registered_tools():
    labels = tool_label_map()
    assert labels["query_business_data"] == "sql"
    assert labels["manage_permission"] == "permission"
    assert labels["query_audit_history"] == "audit"


def test_tool_label_map_values_are_short_role_labels():
    # 외부 노출 라벨은 역할(role) 기반 소문자 단어 (ADR-0033)
    for label in tool_label_map().values():
        assert label.islower()
        assert " " not in label
