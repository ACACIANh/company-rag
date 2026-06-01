from unittest.mock import AsyncMock, MagicMock

from app.graph.nodes.permission import permission_node


def _mock_fga_client(folders):
    client = MagicMock()
    client.get_readable_folders = AsyncMock(return_value=folders)
    return client


async def test_permission_node_sets_allowed_folders():
    fga_client = _mock_fga_client(["/company", "/engineering"])

    result = await permission_node({"user_id": "u1"}, fga_client=fga_client)

    assert result["allowed_folders"] == ["/company", "/engineering"]
    fga_client.get_readable_folders.assert_called_once_with("u1")


async def test_permission_node_empty_when_no_folders():
    fga_client = _mock_fga_client([])

    result = await permission_node({"user_id": "u2"}, fga_client=fga_client)

    assert result["allowed_folders"] == []
