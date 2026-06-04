import pytest
from unittest.mock import AsyncMock, patch

from core.fga.client import FGAClient
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


def test_build_pg_filter_single_folder_exact_match():
    client = _client()
    clause, params = client.build_pg_filter(["/company/hr"])
    # 정확 매칭 — path-prefix(LIKE) 확장 금지. private 하위가 새지 않도록.
    assert clause == "path = ANY($1)"
    assert params == [["/company/hr"]]


def test_build_pg_filter_multiple_folders_exact_match():
    client = _client()
    clause, params = client.build_pg_filter(["/company/common", "/company/engineering"])
    assert clause == "path = ANY($1)"
    assert params == [["/company/common", "/company/engineering"]]


@pytest.mark.asyncio
async def test_user_roles_strips_prefix():
    client = _client()
    with patch.object(client, "_list_fga_objects",
                      new=AsyncMock(return_value=["role:c_level", "role:admin"])) as mock_list:
        roles = await client.user_roles("user-admin")
    assert roles == ["c_level", "admin"]
    mock_list.assert_awaited_once_with("user:user-admin", "member", "role")


@pytest.mark.asyncio
async def test_user_departments_strips_prefix():
    client = _client()
    with patch.object(client, "_list_fga_objects",
                      new=AsyncMock(return_value=["department:개발팀", "department:제품팀"])) as mock_list:
        depts = await client.user_departments("user-junseo")
    assert depts == ["개발팀", "제품팀"]
    mock_list.assert_awaited_once_with("user:user-junseo", "member", "department")


@pytest.mark.asyncio
async def test_user_roles_empty():
    client = _client()
    with patch.object(client, "_list_fga_objects", new=AsyncMock(return_value=[])):
        assert await client.user_roles("user-seoyeon") == []


@pytest.mark.asyncio
async def test_get_readable_folders_returns_cached():
    cache = InMemoryCacheBackend()
    await cache.set("u1", ["/company", "/company/engineering"], ttl_seconds=60)
    client = FGAClient(config=FGAConfig(api_url="http://localhost", store_id="s"), cache=cache)

    with patch.object(client, "list_readable_folders", new=AsyncMock()) as mock_list:
        result = await client.get_readable_folders("u1")

    mock_list.assert_not_called()  # 캐시 히트 → ListObjects 안 때림
    assert result == ["/company", "/company/engineering"]


@pytest.mark.asyncio
async def test_get_readable_folders_fetches_and_caches_raw_on_miss():
    cache = InMemoryCacheBackend()
    client = FGAClient(config=FGAConfig(api_url="http://localhost", store_id="s"), cache=cache)

    # ListObjects가 상속까지 풀어 반환한 폴더 목록을 prune 없이 그대로 사용한다.
    # (상위 가시성이 하위 가시성을 함의하지 않으므로 — private 폴더 차단 유지)
    raw = ["/company", "/company/engineering", "/company/engineering/ops"]
    with patch.object(client, "list_readable_folders", new=AsyncMock(return_value=raw)):
        result = await client.get_readable_folders("u2")

    assert result == raw  # prune으로 합치지 않음
    assert await cache.get("u2") == raw


@pytest.mark.asyncio
async def test_check_returns_allowed_true():
    client = _client()

    class _Resp:
        allowed = True

    class _FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def check(self, req):
            assert req.user == "user:alice"
            assert req.relation == "allow_select"
            assert getattr(req, "object") == "capability:sql"
            return _Resp()

    with patch("openfga_sdk.OpenFgaClient", return_value=_FakeClient()):
        result = await client.check("user:alice", "allow_select", "capability:sql")
    assert result is True


@pytest.mark.asyncio
async def test_check_with_api_key_builds_credentials():
    config = FGAConfig(api_url="http://localhost:8080", store_id="s", api_key="secret-token")
    client = FGAClient(config=config, cache=InMemoryCacheBackend())

    class _Resp:
        allowed = True

    class _FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def check(self, req): return _Resp()

    with patch("openfga_sdk.OpenFgaClient", return_value=_FakeClient()):
        # api_key 경로(Credentials 생성)를 타면서 예외 없이 통과해야 한다
        result = await client.check("user:alice", "allow_select", "capability:sql")
    assert result is True


@pytest.mark.asyncio
async def test_check_returns_allowed_false():
    client = _client()

    class _Resp:
        allowed = False

    class _FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def check(self, req):
            assert req.user == "user:bob"
            assert req.relation == "justify_ddl"
            assert getattr(req, "object") == "capability:sql"
            return _Resp()

    with patch("openfga_sdk.OpenFgaClient", return_value=_FakeClient()):
        result = await client.check("user:bob", "justify_ddl", "capability:sql")
    assert result is False


@pytest.mark.asyncio
async def test_grant_tuple_writes_and_invalidates():
    client = _client()
    with patch.object(client, "_write_fga_tuples", new=AsyncMock()) as mock_write, \
         patch.object(client._cache, "invalidate", new=AsyncMock()) as mock_inv:
        await client.grant_tuple("user:user-jisoo", "member", "department:개발팀")
    mock_write.assert_awaited_once_with([
        {"user": "user:user-jisoo", "relation": "member", "object": "department:개발팀"}
    ])
    mock_inv.assert_awaited_once()


@pytest.mark.asyncio
async def test_revoke_tuple_deletes_and_invalidates():
    client = _client()

    class _FakeClient:
        def __init__(self):
            self.deleted = None
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def write(self, req):
            self.deleted = req

    fake = _FakeClient()
    with patch("openfga_sdk.OpenFgaClient", return_value=fake), \
         patch.object(client._cache, "invalidate", new=AsyncMock()) as mock_inv:
        await client.revoke_tuple("user:user-jisoo", "member", "department:개발팀")
    assert fake.deleted is not None          # deletes 요청이 전달됨
    mock_inv.assert_awaited_once()
