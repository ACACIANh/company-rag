import pytest
from unittest.mock import AsyncMock, patch

from core.fga.client import FGAClient, prune_to_top_folders
from core.fga.models import FGAConfig
from core.fga.cache.memory import InMemoryCacheBackend


def _client() -> FGAClient:
    config = FGAConfig(api_url="http://localhost:8080", store_id="test-store")
    return FGAClient(config=config, cache=InMemoryCacheBackend())


def test_build_pg_filter_empty_returns_false():
    client = _client()
    clause, params = client.build_pg_filter([])
    assert clause == "FALSE"
    assert params == []


def test_build_pg_filter_single_folder_prefix():
    client = _client()
    clause, params = client.build_pg_filter(["/engineering"])
    assert "path = $1" in clause
    assert "path LIKE $2" in clause
    assert params == ["/engineering", "/engineering/%"]


def test_build_pg_filter_multiple_folders():
    client = _client()
    clause, params = client.build_pg_filter(["/company", "/engineering"])
    assert params == ["/company", "/company/%", "/engineering", "/engineering/%"]
    assert "$3" in clause and "$4" in clause
    assert " OR " in clause


def test_prune_drops_descendants():
    assert prune_to_top_folders(["/a", "/a/b", "/a/b/c", "/x"]) == ["/a", "/x"]


def test_prune_no_false_prefix():
    assert prune_to_top_folders(["/a", "/ab"]) == ["/a", "/ab"]


@pytest.mark.asyncio
async def test_get_readable_folders_returns_cached():
    cache = InMemoryCacheBackend()
    await cache.set("u1", ["/company", "/engineering"], ttl_seconds=60)
    client = FGAClient(config=FGAConfig(api_url="http://localhost", store_id="s"), cache=cache)

    with patch.object(client, "list_readable_folders", new=AsyncMock()) as mock_list:
        result = await client.get_readable_folders("u1")

    mock_list.assert_not_called()  # 캐시 히트 → ListObjects 안 때림
    assert result == ["/company", "/engineering"]


@pytest.mark.asyncio
async def test_get_readable_folders_fetches_prunes_and_caches_on_miss():
    cache = InMemoryCacheBackend()
    client = FGAClient(config=FGAConfig(api_url="http://localhost", store_id="s"), cache=cache)

    with patch.object(
        client, "list_readable_folders",
        new=AsyncMock(return_value=["/company", "/engineering", "/engineering/ops"]),
    ):
        result = await client.get_readable_folders("u2")

    assert result == ["/company", "/engineering"]  # ops 추려짐
    assert await cache.get("u2") == ["/company", "/engineering"]  # 캐시에 적재
