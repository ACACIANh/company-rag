from unittest.mock import patch

from shared.fga.client import FGAClient
from shared.fga.models import FGAConfig, UserPermission
from shared.fga.cache.memory import InMemoryCacheBackend


def _client() -> FGAClient:
    config = FGAConfig(api_url="http://localhost:8080", store_id="test-store")
    return FGAClient(config=config, cache=InMemoryCacheBackend())


def test_build_chroma_filter_public_only():
    """팀도 개인문서도 없으면 public 문서만 반환."""
    client = _client()
    perm = UserPermission(user_id="u1", teams=[], personal_docs=[])
    result = client.build_chroma_filter(perm)
    assert result == {"sensitivity": "public"}


def test_build_chroma_filter_with_teams():
    """팀이 있으면 public + internal(팀 필터) 포함."""
    client = _client()
    perm = UserPermission(user_id="u1", teams=["team:dev", "team:ops"], personal_docs=[])
    result = client.build_chroma_filter(perm)
    assert result == {
        "$or": [
            {"sensitivity": "public"},
            {"$and": [{"team_id": {"$in": ["team:dev", "team:ops"]}}, {"sensitivity": "internal"}]},
        ]
    }


def test_build_chroma_filter_with_personal_docs():
    """개인 문서가 있으면 secret 조건 포함."""
    client = _client()
    perm = UserPermission(user_id="u1", teams=[], personal_docs=["doc:salary"])
    result = client.build_chroma_filter(perm)
    assert result == {
        "$or": [
            {"sensitivity": "public"},
            {"$and": [{"sensitivity": "secret"}, {"document_id": {"$in": ["doc:salary"]}}]},
        ]
    }


def test_build_chroma_filter_full():
    """팀 + 개인 문서 모두 있으면 세 조건 모두 포함."""
    client = _client()
    perm = UserPermission(
        user_id="u1",
        teams=["team:dev"],
        personal_docs=["doc:review"],
    )
    result = client.build_chroma_filter(perm)
    assert result == {
        "$or": [
            {"sensitivity": "public"},
            {"$and": [{"team_id": {"$in": ["team:dev"]}}, {"sensitivity": "internal"}]},
            {"$and": [{"sensitivity": "secret"}, {"document_id": {"$in": ["doc:review"]}}]},
        ]
    }


def test_get_permission_returns_cached():
    """캐시 히트 시 FGA API 호출 없이 반환."""
    cache = InMemoryCacheBackend()
    perm = UserPermission(user_id="u1", teams=["team:dev"], personal_docs=[])
    cache.set("u1", perm, ttl_seconds=60)
    client = FGAClient(config=FGAConfig(api_url="http://localhost", store_id="s"), cache=cache)

    with patch.object(client, "_fetch_from_fga") as mock_fetch:
        result = client.get_permission("u1")

    mock_fetch.assert_not_called()
    assert result.teams == ["team:dev"]


def test_get_permission_calls_fga_on_cache_miss():
    """캐시 미스 시 _fetch_from_fga 호출 후 캐시에 저장."""
    cache = InMemoryCacheBackend()
    client = FGAClient(config=FGAConfig(api_url="http://localhost", store_id="s"), cache=cache)
    expected = UserPermission(user_id="u2", teams=["team:hr"], personal_docs=["doc:eval"])

    with patch.object(client, "_fetch_from_fga", return_value=expected):
        result = client.get_permission("u2")

    assert result.teams == ["team:hr"]
    cached = cache.get("u2")
    assert cached is not None
    assert cached.teams == ["team:hr"]


def test_write_tuples_invalidates_cache():
    """write_tuples 후 owner의 캐시가 무효화된다."""
    cache = InMemoryCacheBackend()
    perm = UserPermission(user_id="owner1", teams=["team:dev"], personal_docs=[])
    cache.set("owner1", perm, ttl_seconds=60)
    client = FGAClient(config=FGAConfig(api_url="http://localhost", store_id="s"), cache=cache)

    with patch.object(client, "_write_fga_tuples"):
        client.write_tuples("doc:x", "owner1", "team:dev", "internal")

    assert cache.get("owner1") is None


def test_filter_sources_public_always_accessible():
    """public 문서는 팀/개인문서 없이도 항상 접근 가능."""
    from shared.models import SourceRef
    from unittest.mock import patch

    client = _client()
    perm = UserPermission(user_id="u1", teams=[], personal_docs=[])
    src = SourceRef(source="pub.md", sensitivity="public")

    with patch.object(client, "get_permission", return_value=perm):
        result = client.filter_sources([src], "u1")

    assert result == [src]


def test_filter_sources_internal_requires_team():
    """internal 문서는 팀 멤버만 접근 가능."""
    from shared.models import SourceRef
    from unittest.mock import patch

    client = _client()
    perm_member = UserPermission(user_id="u1", teams=["team:dev"], personal_docs=[])
    perm_non_member = UserPermission(user_id="u2", teams=[], personal_docs=[])
    src = SourceRef(source="int.md", sensitivity="internal", team_id="team:dev")

    with patch.object(client, "get_permission", return_value=perm_member):
        assert client.filter_sources([src], "u1") == [src]

    with patch.object(client, "get_permission", return_value=perm_non_member):
        assert client.filter_sources([src], "u2") == []


def test_filter_sources_secret_requires_personal_doc():
    """secret 문서는 개인 허용 목록에 있는 경우만 접근 가능."""
    from shared.models import SourceRef
    from unittest.mock import patch

    client = _client()
    perm_allowed = UserPermission(user_id="u1", teams=[], personal_docs=["doc:salary"])
    perm_denied = UserPermission(user_id="u2", teams=[], personal_docs=[])
    src = SourceRef(source="sec.md", sensitivity="secret", document_id="doc:salary")

    with patch.object(client, "get_permission", return_value=perm_allowed):
        assert client.filter_sources([src], "u1") == [src]

    with patch.object(client, "get_permission", return_value=perm_denied):
        assert client.filter_sources([src], "u2") == []


def test_filter_sources_unknown_sensitivity_blocked():
    """알 수 없는 sensitivity는 접근 불가로 처리."""
    from shared.models import SourceRef
    from unittest.mock import patch

    client = _client()
    perm = UserPermission(user_id="u1", teams=["team:dev"], personal_docs=["doc:x"])
    src = SourceRef(source="unknown.md", sensitivity="classified")

    with patch.object(client, "get_permission", return_value=perm):
        result = client.filter_sources([src], "u1")

    assert result == []


def test_filter_sources_empty_list():
    """빈 목록 입력 시 FGA 조회 없이 빈 목록 반환."""
    from unittest.mock import patch

    client = _client()

    with patch.object(client, "get_permission") as mock_perm:
        result = client.filter_sources([], "u1")

    mock_perm.assert_not_called()
    assert result == []
