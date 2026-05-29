from unittest.mock import AsyncMock, MagicMock

from shared.fga.models import UserPermission
from app.graph.nodes.permission import permission_node


def _mock_fga_client(teams=None, personal_docs=None):
    client = MagicMock()
    client.get_permission = AsyncMock(return_value=UserPermission(
        user_id="u1",
        teams=["team:dev"] if teams is None else teams,
        personal_docs=[] if personal_docs is None else personal_docs,
    ))
    return client


async def test_permission_node_populates_state():
    state = {"user_id": "u1"}
    fga_client = _mock_fga_client(teams=["team:dev"], personal_docs=["doc:secret"])

    result = await permission_node(state, fga_client=fga_client)

    assert result["user_teams"] == ["team:dev"]
    assert result["personal_doc_ids"] == ["doc:secret"]
    fga_client.get_permission.assert_called_once_with("u1")


async def test_permission_node_empty_when_no_permissions():
    state = {"user_id": "u2"}
    fga_client = _mock_fga_client(teams=[], personal_docs=[])

    result = await permission_node(state, fga_client=fga_client)

    assert result["user_teams"] == []
    assert result["personal_doc_ids"] == []
