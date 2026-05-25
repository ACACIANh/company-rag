import os
import pytest
from shared.fga.cache.postgres import PostgresCacheBackend
from shared.fga.models import UserPermission


@pytest.fixture
def pg_cache():
    dsn = os.environ.get("POSTGRES_DSN", "")
    if not dsn:
        pytest.skip("POSTGRES_DSN not set")
    cache = PostgresCacheBackend(dsn=dsn)
    cache._ensure_table()
    cache.invalidate("test_u1")  # 이전 테스트 잔류 정리
    yield cache
    cache.invalidate("test_u1")


def test_pg_set_and_get(pg_cache):
    perm = UserPermission(user_id="test_u1", teams=["team:dev"], personal_docs=["doc:x"])
    pg_cache.set("test_u1", perm, ttl_seconds=60)
    result = pg_cache.get("test_u1")
    assert result is not None
    assert result.teams == ["team:dev"]
    assert result.personal_docs == ["doc:x"]


def test_pg_expired_returns_none(pg_cache):
    perm = UserPermission(user_id="test_u1", teams=[], personal_docs=[])
    pg_cache.set("test_u1", perm, ttl_seconds=-1)  # 이미 만료
    assert pg_cache.get("test_u1") is None


def test_pg_invalidate(pg_cache):
    perm = UserPermission(user_id="test_u1", teams=["team:ops"], personal_docs=[])
    pg_cache.set("test_u1", perm, ttl_seconds=60)
    pg_cache.invalidate("test_u1")
    assert pg_cache.get("test_u1") is None
