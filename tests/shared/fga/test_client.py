import pytest
from unittest.mock import AsyncMock, patch

from shared.fga.client import FGAClient
from shared.fga.models import FGAConfig, UserPermission
from shared.fga.cache.memory import InMemoryCacheBackend
from shared.models import SourceRef


def _client() -> FGAClient:
    config = FGAConfig(api_url="http://localhost:8080", store_id="test-store")
    return FGAClient(config=config, cache=InMemoryCacheBackend())


def test_build_pg_filter_public_only():
    client = _client()
    perm = UserPermission(user_id="u1", teams=[], personal_docs=[])
    clause, params = client.build_pg_filter(perm)
    assert "sensitivity = 'public'" in clause
    assert params == []


def test_build_pg_filter_with_teams():
    client = _client()
    perm = UserPermission(user_id="u1", teams=["team:dev", "team:ops"], personal_docs=[])
    clause, params = client.build_pg_filter(perm)
    assert "sensitivity = 'public'" in clause
    assert "team_id = ANY" in clause
    assert "sensitivity = 'internal'" in clause
    assert ["team:dev", "team:ops"] in params


def test_build_pg_filter_with_personal_docs():
    client = _client()
    perm = UserPermission(user_id="u1", teams=[], personal_docs=["doc:salary"])
    clause, params = client.build_pg_filter(perm)
    assert "sensitivity = 'public'" in clause
    assert "doc_id = ANY" in clause
    assert ["doc:salary"] in params


def test_build_pg_filter_full():
    client = _client()
    perm = UserPermission(user_id="u1", teams=["team:dev"], personal_docs=["doc:review"])
    clause, params = client.build_pg_filter(perm)
    assert "sensitivity = 'public'" in clause
    assert "team_id = ANY" in clause
    assert "doc_id = ANY" in clause
    assert ["team:dev"] in params
    assert ["doc:review"] in params


@pytest.mark.asyncio
async def test_get_permission_returns_cached():
    cache = InMemoryCacheBackend()
    perm = UserPermission(user_id="u1", teams=["team:dev"], personal_docs=[])
    await cache.set("u1", perm, ttl_seconds=60)
    client = FGAClient(config=FGAConfig(api_url="http://localhost", store_id="s"), cache=cache)

    with patch.object(client, "_fetch_from_fga", new=AsyncMock()) as mock_fetch:
        result = await client.get_permission("u1")

    mock_fetch.assert_not_called()
    assert result.teams == ["team:dev"]


@pytest.mark.asyncio
async def test_get_permission_calls_fga_on_cache_miss():
    cache = InMemoryCacheBackend()
    client = FGAClient(config=FGAConfig(api_url="http://localhost", store_id="s"), cache=cache)
    expected = UserPermission(user_id="u2", teams=["team:hr"], personal_docs=["doc:eval"])

    with patch.object(client, "_fetch_from_fga", new=AsyncMock(return_value=expected)):
        result = await client.get_permission("u2")

    assert result.teams == ["team:hr"]
    cached = await cache.get("u2")
    assert cached is not None
    assert cached.teams == ["team:hr"]


@pytest.mark.asyncio
async def test_write_tuples_invalidates_cache():
    cache = InMemoryCacheBackend()
    perm = UserPermission(user_id="owner1", teams=["team:dev"], personal_docs=[])
    await cache.set("owner1", perm, ttl_seconds=60)
    client = FGAClient(config=FGAConfig(api_url="http://localhost", store_id="s"), cache=cache)

    with patch.object(client, "_write_fga_tuples", new=AsyncMock()):
        await client.write_tuples("doc:x", "owner1", "team:dev", "internal")

    assert await cache.get("owner1") is None


def test_filter_sources_public_always_accessible():
    client = _client()
    perm = UserPermission(user_id="u1", teams=[], personal_docs=[])
    src = SourceRef(source="pub.md", sensitivity="public")
    assert client._is_accessible(src, perm) is True


def test_filter_sources_internal_requires_team():
    client = _client()
    perm_member = UserPermission(user_id="u1", teams=["team:dev"], personal_docs=[])
    perm_non_member = UserPermission(user_id="u2", teams=[], personal_docs=[])
    src = SourceRef(source="int.md", sensitivity="internal", team_id="team:dev")
    assert client._is_accessible(src, perm_member) is True
    assert client._is_accessible(src, perm_non_member) is False


def test_filter_sources_secret_requires_personal_doc():
    client = _client()
    perm_allowed = UserPermission(user_id="u1", teams=[], personal_docs=["doc:salary"])
    perm_denied = UserPermission(user_id="u2", teams=[], personal_docs=[])
    src = SourceRef(source="sec.md", sensitivity="secret", document_id="doc:salary")
    assert client._is_accessible(src, perm_allowed) is True
    assert client._is_accessible(src, perm_denied) is False
