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
