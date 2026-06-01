import time

from core.fga.cache.memory import InMemoryCacheBackend

_FOLDERS = ["/company", "/engineering"]


async def test_set_and_get_returns_folders():
    cache = InMemoryCacheBackend()
    await cache.set("u1", _FOLDERS, ttl_seconds=60)
    result = await cache.get("u1")
    assert result == _FOLDERS


async def test_get_returns_none_for_unknown_user():
    cache = InMemoryCacheBackend()
    assert await cache.get("unknown") is None


async def test_ttl_expiry_returns_none():
    cache = InMemoryCacheBackend()
    await cache.set("u1", _FOLDERS, ttl_seconds=1)
    time.sleep(1.1)
    assert await cache.get("u1") is None


async def test_invalidate_removes_entry():
    cache = InMemoryCacheBackend()
    await cache.set("u1", _FOLDERS, ttl_seconds=60)
    await cache.invalidate("u1")
    assert await cache.get("u1") is None


async def test_invalidate_nonexistent_is_noop():
    cache = InMemoryCacheBackend()
    await cache.invalidate("ghost")  # should not raise
