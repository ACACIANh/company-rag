from unittest.mock import AsyncMock, MagicMock

from app.graph.nodes.capability_node import capability_node


def _mock_fga(can_grant: bool) -> MagicMock:
    client = MagicMock()
    client.check = AsyncMock(return_value=can_grant)
    return client


def _mock_audit(counts: dict) -> MagicMock:
    sink = MagicMock()
    sink.count_by_decision = AsyncMock(return_value=counts)
    return sink


async def test_capability_node_admin_text_when_can_grant():
    fga_client = _mock_fga(True)

    result = await capability_node({"user_id": "joohwan"}, fga_client=fga_client)

    fga_client.check.assert_called_once_with("user:joohwan", "justify_grant", "capability:admin")
    assert "권한 관리" in result["answer"]
    assert "부여" in result["answer"]
    assert result["citations"] == []


async def test_capability_node_user_text_when_cannot_grant():
    fga_client = _mock_fga(False)

    result = await capability_node({"user_id": "minjun"}, fga_client=fga_client)

    fga_client.check.assert_called_once_with("user:minjun", "justify_grant", "capability:admin")
    assert "권한 확인" in result["answer"]
    assert "부여" not in result["answer"]
    assert result["citations"] == []


async def test_admin_gets_audit_summary_when_sink_present():
    fga_client = _mock_fga(True)
    audit = _mock_audit({"ALLOW": 15, "DENY": 3, "JUSTIFY_AND_APPROVE": 5})

    result = await capability_node({"user_id": "joohwan"}, fga_client=fga_client, audit_sink=audit)

    audit.count_by_decision.assert_awaited_once()
    assert "총 23건" in result["answer"]
    assert "ALLOW 15" in result["answer"]
    assert "DENY 3" in result["answer"]
    assert "JUSTIFY 5" in result["answer"]


async def test_non_admin_never_queries_audit():
    fga_client = _mock_fga(False)
    audit = _mock_audit({"ALLOW": 1})

    result = await capability_node({"user_id": "minjun"}, fga_client=fga_client, audit_sink=audit)

    audit.count_by_decision.assert_not_called()
    assert "총" not in result["answer"]
