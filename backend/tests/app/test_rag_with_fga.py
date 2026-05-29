"""
FGA 권한별 PostgreSQL 검색 통합 테스트.
AsyncMock retriever + InMemoryCacheBackend + FGA API mock 사용.
"""
import time
from unittest.mock import AsyncMock

from core.fga.cache.memory import InMemoryCacheBackend
from core.fga.client import FGAClient
from core.fga.models import FGAConfig, UserPermission
from core.models import Chunk, SearchResult


def _make_fga_client(teams=None, personal_docs=None) -> FGAClient:
    config = FGAConfig(api_url="http://localhost", store_id="test")
    cache = InMemoryCacheBackend()
    perm = UserPermission(user_id="u1", teams=teams or [], personal_docs=personal_docs or [])
    # InMemoryCacheBackend는 내부적으로 dict를 사용 — 직접 seeding
    cache._store["u1"] = (perm, time.time() + 3600)
    return FGAClient(config=config, cache=cache)


def _mock_retriever(chunks: list[dict]):
    """
    pg filter 기반 retriever mock.
    where_clause / params 로 sensitivity 필터링을 직접 시뮬레이션.
    """
    mock = AsyncMock()

    async def fake_retrieve(query, top_k=5, where_clause="", params=None):
        params = params or []
        results = []
        for c in chunks:
            sensitivity = c["sensitivity"]
            team_id = c.get("team_id", "")
            doc_id = c.get("doc_id", f"doc:{c['source']}")

            if sensitivity == "public":
                pass
            elif sensitivity == "internal":
                allowed_teams = params[0] if len(params) >= 1 else []
                if team_id not in allowed_teams:
                    continue
            elif sensitivity == "secret":
                allowed_docs = params[-1] if params else []
                if doc_id not in allowed_docs:
                    continue
            else:
                continue

            results.append(SearchResult(
                chunk=Chunk(text=c["text"], source=c["source"], chunk_id=c["source"]),
                score=0.9,
            ))
        return results[:top_k]

    mock.retrieve = fake_retrieve
    return mock


async def test_public_doc_accessible_to_all():
    fga = _make_fga_client(teams=[], personal_docs=[])
    retriever = _mock_retriever([
        {"text": "공개 내용", "source": "public.md", "sensitivity": "public"},
    ])

    from app.graph.nodes.permission import permission_node
    from app.graph.nodes.retrieve import retrieve_node

    state = {"user_id": "u1", "question": "공개 문서", "user_teams": [], "personal_doc_ids": []}
    perm_result = await permission_node(state, fga_client=fga)
    state.update(perm_result)
    result = await retrieve_node(state, retriever=retriever, fga_client=fga)

    assert len(result["documents"]) == 1
    assert result["documents"][0].chunk.source == "public.md"


async def test_internal_doc_blocked_without_team():
    fga = _make_fga_client(teams=[], personal_docs=[])
    retriever = _mock_retriever([
        {"text": "내부 내용", "source": "internal.md", "sensitivity": "internal", "team_id": "team:dev"},
    ])

    from app.graph.nodes.permission import permission_node
    from app.graph.nodes.retrieve import retrieve_node

    state = {"user_id": "u1", "question": "내부 문서", "user_teams": [], "personal_doc_ids": []}
    perm_result = await permission_node(state, fga_client=fga)
    state.update(perm_result)
    result = await retrieve_node(state, retriever=retriever, fga_client=fga)

    assert len(result["documents"]) == 0


async def test_internal_doc_accessible_with_correct_team():
    fga = _make_fga_client(teams=["team:dev"], personal_docs=[])
    retriever = _mock_retriever([
        {"text": "팀 내부", "source": "internal.md", "sensitivity": "internal", "team_id": "team:dev"},
        {"text": "공개", "source": "public.md", "sensitivity": "public"},
    ])

    from app.graph.nodes.permission import permission_node
    from app.graph.nodes.retrieve import retrieve_node

    state = {"user_id": "u1", "question": "팀 문서", "user_teams": [], "personal_doc_ids": []}
    perm_result = await permission_node(state, fga_client=fga)
    state.update(perm_result)
    result = await retrieve_node(state, retriever=retriever, fga_client=fga)

    sources = [r.chunk.source for r in result["documents"]]
    assert "internal.md" in sources
    assert "public.md" in sources


async def test_secret_doc_accessible_only_with_personal_doc_id():
    fga = _make_fga_client(teams=[], personal_docs=["doc:salary.md"])
    retriever = _mock_retriever([
        {"text": "급여 내역", "source": "salary.md", "sensitivity": "secret", "doc_id": "doc:salary.md"},
    ])

    from app.graph.nodes.permission import permission_node
    from app.graph.nodes.retrieve import retrieve_node

    state = {"user_id": "u1", "question": "급여", "user_teams": [], "personal_doc_ids": []}
    perm_result = await permission_node(state, fga_client=fga)
    state.update(perm_result)
    result = await retrieve_node(state, retriever=retriever, fga_client=fga)

    assert len(result["documents"]) == 1
    assert result["documents"][0].chunk.source == "salary.md"


async def test_secret_doc_blocked_without_personal_doc_id():
    fga = _make_fga_client(teams=[], personal_docs=[])
    retriever = _mock_retriever([
        {"text": "급여 내역", "source": "salary.md", "sensitivity": "secret", "doc_id": "doc:salary.md"},
    ])

    from app.graph.nodes.permission import permission_node
    from app.graph.nodes.retrieve import retrieve_node

    state = {"user_id": "u1", "question": "급여", "user_teams": [], "personal_doc_ids": []}
    perm_result = await permission_node(state, fga_client=fga)
    state.update(perm_result)
    result = await retrieve_node(state, retriever=retriever, fga_client=fga)

    assert len(result["documents"]) == 0
