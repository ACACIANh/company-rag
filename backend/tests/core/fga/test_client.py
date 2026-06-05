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
                      new=AsyncMock(return_value=["department:개발", "department:제품"])) as mock_list:
        depts = await client.user_departments("user-mido")
    assert depts == ["개발", "제품"]
    mock_list.assert_awaited_once_with("user:user-mido", "member", "department")


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
        await client.grant_tuple("user:user-joohwan", "member", "department:개발")
    mock_write.assert_awaited_once_with([
        {"user": "user:user-joohwan", "relation": "member", "object": "department:개발"}
    ])
    mock_inv.assert_awaited_once()


@pytest.mark.asyncio
async def test_grant_tuple_invalidates_bare_user_id():
    # 폴더 캐시는 bare user id로 키잉되므로(get_readable_folders(user_id)),
    # 무효화도 "user:" 접두사를 떼고 bare id로 해야 키가 맞는다.
    client = _client()
    with patch.object(client, "_write_fga_tuples", new=AsyncMock()), \
         patch.object(client._cache, "invalidate", new=AsyncMock()) as mock_inv:
        await client.grant_tuple("user:user-alice", "can_read", "folder:/company/hr")
    mock_inv.assert_awaited_once_with("user-alice")


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
        await client.revoke_tuple("user:user-joohwan", "member", "department:개발")
    assert fake.deleted is not None          # deletes 요청이 전달됨
    mock_inv.assert_awaited_once()


@pytest.mark.asyncio
async def test_revoke_tuple_invalidates_bare_user_id():
    client = _client()

    class _FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def write(self, req): pass

    with patch("openfga_sdk.OpenFgaClient", return_value=_FakeClient()), \
         patch.object(client._cache, "invalidate", new=AsyncMock()) as mock_inv:
        await client.revoke_tuple("user:user-alice", "can_read", "folder:/company/hr")
    mock_inv.assert_awaited_once_with("user-alice")


@pytest.mark.asyncio
async def test_grant_revoke_roundtrip_invalidates_cache():
    """ADR-0046 revoke 종단: grant→캐시 무효화→재캐시→revoke→캐시 무효화 왕복.

    실제 InMemoryCacheBackend로 부여·회수가 모두 폴더 캐시를 즉시 비우는지 종단 확인.
    """
    cache = InMemoryCacheBackend()
    await cache.set("user-joohwan", ["/company"], ttl_seconds=60)
    client = FGAClient(config=FGAConfig(api_url="http://localhost", store_id="s"), cache=cache)

    class _FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def write(self, req): pass

    with patch("openfga_sdk.OpenFgaClient", return_value=_FakeClient()), \
         patch.object(client, "_write_fga_tuples", new=AsyncMock()):
        await client.grant_tuple("user:user-joohwan", "member", "department:개발")
        assert await cache.get("user-joohwan") is None       # grant가 캐시를 비움

        await cache.set("user-joohwan", ["/company"], ttl_seconds=60)
        await client.revoke_tuple("user:user-joohwan", "member", "department:개발")
        assert await cache.get("user-joohwan") is None       # revoke도 캐시를 비움


def _member_read_fake(member_users: list[str], dept_object: str):
    """OpenFGA Read를 흉내내 (object=dept, relation=member) 멤버 튜플을 1페이지로 반환하는 fake.
    write(deletes)는 no-op. grant/revoke 양쪽 무효화 테스트에 공용."""
    from types import SimpleNamespace

    class _FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def write(self, req): pass
        async def read(self, body, options=None):
            tuples = [
                SimpleNamespace(key=SimpleNamespace(user=u, relation="member", object=dept_object))
                for u in member_users
            ]
            return SimpleNamespace(tuples=tuples, continuation_token="")
    return _FakeClient()


@pytest.mark.asyncio
async def test_grant_tuple_set_subject_invalidates_all_department_members():
    """department:D#member 를 holder로 권한 부여 시, 그 부서 멤버 전원의 폴더 캐시가
    무효화돼야 한다(TTU 파급 — ADR-0051 보강). bare user id로 키잉됨."""
    cache = InMemoryCacheBackend()
    await cache.set("daesu", ["/company/hr"], ttl_seconds=60)
    await cache.set("mido", ["/company/hr"], ttl_seconds=60)
    client = FGAClient(config=FGAConfig(api_url="http://localhost", store_id="s"), cache=cache)

    fake = _member_read_fake(["user:daesu", "user:mido"], "department:인사")
    with patch("openfga_sdk.OpenFgaClient", return_value=fake), \
         patch.object(client, "_write_fga_tuples", new=AsyncMock()):
        await client.grant_tuple("department:인사#member", "holder", "permission:인사")

    assert await cache.get("daesu") is None
    assert await cache.get("mido") is None


@pytest.mark.asyncio
async def test_revoke_tuple_set_subject_invalidates_all_department_members():
    """보안 핵심: department:D#member 권한 회수 시, 부서원 전원 캐시를 즉시 비워야
    회수된 폴더가 TTL까지 RAG pre-filter에 계속 노출되는 누수를 막는다."""
    cache = InMemoryCacheBackend()
    await cache.set("daesu", ["/company/hr"], ttl_seconds=60)
    await cache.set("mido", ["/company/hr"], ttl_seconds=60)
    client = FGAClient(config=FGAConfig(api_url="http://localhost", store_id="s"), cache=cache)

    fake = _member_read_fake(["user:daesu", "user:mido"], "department:인사")
    with patch("openfga_sdk.OpenFgaClient", return_value=fake):
        await client.revoke_tuple("department:인사#member", "holder", "permission:인사")

    assert await cache.get("daesu") is None
    assert await cache.get("mido") is None


@pytest.mark.asyncio
async def test_revoke_tuple_role_member_invalidates_role_members():
    """role:R#member 도 super_reader(model.fga)로 폴더 can_read 경로가 있으므로, no-op이면
    seed_fga --prune의 super_reader revoke가 누수된다. #member userset은 종류 불문 멤버 무효화."""
    cache = InMemoryCacheBackend()
    await cache.set("ceo", ["/company"], ttl_seconds=60)
    client = FGAClient(config=FGAConfig(api_url="http://localhost", store_id="s"), cache=cache)

    fake = _member_read_fake(["user:ceo"], "role:c_level")
    with patch("openfga_sdk.OpenFgaClient", return_value=fake):
        await client.revoke_tuple("role:c_level#member", "super_reader", "folder:/company")

    assert await cache.get("ceo") is None


@pytest.mark.asyncio
async def test_revoke_tuple_fails_closed_when_member_read_raises():
    """보안 fail-closed: 집합 revoke 시 멤버 열거(Read)가 실패하면 FGA 삭제는 이미 커밋됐으므로
    캐시를 보수적으로 전체 flush해 회수 폴더가 TTL까지 노출되는 fail-open을 막는다."""
    cache = InMemoryCacheBackend()
    await cache.set("daesu", ["/company/hr"], ttl_seconds=60)
    await cache.set("other", ["/company/x"], ttl_seconds=60)
    client = FGAClient(config=FGAConfig(api_url="http://localhost", store_id="s"), cache=cache)

    class _RaisingReadClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def write(self, req): pass
        async def read(self, body, options=None):
            raise RuntimeError("FGA read transient failure")

    with patch("openfga_sdk.OpenFgaClient", return_value=_RaisingReadClient()):
        await client.revoke_tuple("department:인사#member", "holder", "permission:인사")

    # 멤버를 못 셌으므로 보수적 전체 flush — 무관 사용자 캐시까지 비워짐(fail-closed)
    assert await cache.get("daesu") is None
    assert await cache.get("other") is None


@pytest.mark.asyncio
async def test_revoke_tuple_fails_closed_on_partial_invalidation_failure():
    """무효화 루프가 중간에 실패해도(부분 무효화) 보수적 전체 flush로 fail-closed."""
    cache = InMemoryCacheBackend()
    await cache.set("daesu", ["/company/hr"], ttl_seconds=60)
    await cache.set("other", ["/company/x"], ttl_seconds=60)
    client = FGAClient(config=FGAConfig(api_url="http://localhost", store_id="s"), cache=cache)

    real_invalidate = InMemoryCacheBackend.invalidate

    async def flaky_invalidate(uid):
        if uid == "daesu":
            raise RuntimeError("cache backend hiccup")
        await real_invalidate(cache, uid)

    fake = _member_read_fake(["user:daesu", "user:mido"], "department:인사")
    with patch("openfga_sdk.OpenFgaClient", return_value=fake), \
         patch.object(cache, "invalidate", new=AsyncMock(side_effect=flaky_invalidate)):
        await client.revoke_tuple("department:인사#member", "holder", "permission:인사")

    # 부분 실패 감지 → 전체 flush
    assert await cache.get("other") is None


@pytest.mark.asyncio
async def test_grant_tuple_invalidates_non_user_subject_unchanged():
    # 비-user subject는 "user:"가 없으므로 그대로 전달(무해한 no-op).
    client = _client()
    with patch.object(client, "_write_fga_tuples", new=AsyncMock()), \
         patch.object(client._cache, "invalidate", new=AsyncMock()) as mock_inv:
        await client.grant_tuple("department:eng", "member", "department:org")
    mock_inv.assert_awaited_once_with("department:eng")


def test_client_config_without_api_key_has_no_credentials():
    client = _client()  # api_key 미설정
    cfg = client._client_config()
    assert cfg.api_url == "http://localhost:8080"
    assert cfg.store_id == "test-store"
    assert getattr(cfg, "credentials", None) is None


def test_client_config_with_api_key_builds_credentials():
    config = FGAConfig(api_url="http://localhost:8080", store_id="s", api_key="secret-token")
    client = FGAClient(config=config, cache=InMemoryCacheBackend())
    cfg = client._client_config()
    assert cfg.credentials is not None
    assert cfg.credentials.method == "api_token"
    assert cfg.credentials.configuration.api_token == "secret-token"


@pytest.mark.asyncio
async def test_list_all_tuples_paginates():
    from types import SimpleNamespace
    client = _client()

    def _tup(u, r, o):
        return SimpleNamespace(key=SimpleNamespace(user=u, relation=r, object=o))

    pages = [
        SimpleNamespace(tuples=[_tup("user:a", "member", "department:x")], continuation_token="t1"),
        SimpleNamespace(tuples=[_tup("user:b", "member", "department:y")], continuation_token=""),
    ]
    state = {"i": 0}

    class _FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def read(self, body, options=None):
            page = pages[state["i"]]
            state["i"] += 1
            return page

    with patch("openfga_sdk.OpenFgaClient", return_value=_FakeClient()):
        result = await client.list_all_tuples()

    assert result == [
        ("user:a", "member", "department:x"),
        ("user:b", "member", "department:y"),
    ]
    assert state["i"] == 2   # 두 페이지 모두 소비(빈 token에서 종료)


# ── user_accessible_tables ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_user_accessible_tables_returns_permitted_only():
    """viewer 보유 테이블만 반환, 미보유는 제외."""
    client = _client()

    async def fake_check(user, relation, object_):
        return object_ == "table:employees" and relation == "viewer"

    with patch.object(client, "check", new=AsyncMock(side_effect=fake_check)):
        result = await client.user_accessible_tables("user-joohwan")

    assert result == ["employees"]


@pytest.mark.asyncio
async def test_user_accessible_tables_all_permitted():
    """모든 테이블 viewer 보유 시 전체 반환."""
    client = _client()

    async def fake_check(user, relation, object_):
        return relation == "viewer"

    with patch.object(client, "check", new=AsyncMock(side_effect=fake_check)):
        result = await client.user_accessible_tables("user-joohwan")

    assert sorted(result) == ["employees", "equipment", "sales"]


@pytest.mark.asyncio
async def test_user_accessible_tables_none_permitted():
    """viewer 미보유 시 빈 리스트 반환."""
    client = _client()

    async def fake_check(user, relation, object_):
        return False

    with patch.object(client, "check", new=AsyncMock(side_effect=fake_check)):
        result = await client.user_accessible_tables("user-joohwan")

    assert result == []
