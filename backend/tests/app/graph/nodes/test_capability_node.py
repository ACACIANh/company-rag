from unittest.mock import AsyncMock, MagicMock

from app.graph.nodes.capability_node import capability_node


def _mock_fga(can_grant: bool) -> MagicMock:
    client = MagicMock()
    client.check = AsyncMock(return_value=can_grant)
    return client


async def test_capability_node_admin_text_when_can_grant():
    fga_client = _mock_fga(True)

    result = await capability_node({"user_id": "jisoo"}, fga_client=fga_client)

    fga_client.check.assert_called_once_with("user:jisoo", "justify_grant", "capability:admin")
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
