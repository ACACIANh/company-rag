"""
FGA 권한별 Chroma 검색 통합 테스트.
실제 Chroma (임베디드) + InMemoryCacheBackend + FGA API mock 사용.
"""
from unittest.mock import MagicMock

from shared.fga.cache.memory import InMemoryCacheBackend
from shared.fga.client import FGAClient
from shared.fga.models import FGAConfig, UserPermission
from shared.models import Chunk, SearchResult


def _make_fga_client(teams=None, personal_docs=None) -> FGAClient:
    config = FGAConfig(api_url="http://localhost", store_id="test")
    client = FGAClient(config=config, cache=InMemoryCacheBackend())
    perm = UserPermission(user_id="u1", teams=teams or [], personal_docs=personal_docs or [])
    client._cache.set("u1", perm, ttl_seconds=60)
    return client


def _mock_retriever(chunks: list[dict]) -> MagicMock:
    """
    chunks: list of dicts with keys:
        text, source, sensitivity, team_id (optional), document_id (optional)
    document_id defaults to f"doc:{source}" if not provided.
    team_id defaults to "" if not provided.
    """
    mock = MagicMock()

    def fake_retrieve(query, top_k=5, where_filter=None):
        results = []
        for chunk_def in chunks:
            text = chunk_def["text"]
            source = chunk_def["source"]
            sensitivity = chunk_def["sensitivity"]
            meta = {
                "sensitivity": sensitivity,
                "source": source,
                "document_id": chunk_def.get("document_id", f"doc:{source}"),
                "team_id": chunk_def.get("team_id", ""),
            }
            if where_filter is None:
                results.append(SearchResult(
                    chunk=Chunk(text=text, source=source, chunk_id=source), score=0.9
                ))
            else:
                if _matches_filter(meta, where_filter):
                    results.append(SearchResult(
                        chunk=Chunk(text=text, source=source, chunk_id=source), score=0.9
                    ))
        return results[:top_k]

    mock.retrieve.side_effect = fake_retrieve
    return mock


def _matches_filter(meta: dict, f: dict) -> bool:
    if "$or" in f:
        return any(_matches_filter(meta, c) for c in f["$or"])
    if "$and" in f:
        return all(_matches_filter(meta, c) for c in f["$and"])
    for key, cond in f.items():
        if isinstance(cond, dict) and "$in" in cond:
            if meta.get(key) not in cond["$in"]:
                return False
        else:
            if meta.get(key) != cond:
                return False
    return True


def test_public_doc_accessible_to_all():
    fga = _make_fga_client(teams=[], personal_docs=[])
    retriever = _mock_retriever([
        {"text": "공개 내용", "source": "public.md", "sensitivity": "public"},
    ])

    from app.graph.nodes.permission import permission_node
    from app.graph.nodes.retrieve import retrieve_node

    state = {"user_id": "u1", "question": "공개 문서", "user_teams": [], "personal_doc_ids": []}
    perm_result = permission_node(state, fga_client=fga)
    state.update(perm_result)
    result = retrieve_node(state, retriever=retriever, fga_client=fga)

    assert len(result["documents"]) == 1
    assert result["documents"][0].chunk.source == "public.md"


def test_internal_doc_blocked_without_team():
    fga = _make_fga_client(teams=[], personal_docs=[])
    retriever = _mock_retriever([
        {"text": "내부 내용", "source": "internal.md", "sensitivity": "internal", "team_id": "team:dev"},
    ])

    from app.graph.nodes.permission import permission_node
    from app.graph.nodes.retrieve import retrieve_node

    state = {"user_id": "u1", "question": "내부 문서", "user_teams": [], "personal_doc_ids": []}
    perm_result = permission_node(state, fga_client=fga)
    state.update(perm_result)
    result = retrieve_node(state, retriever=retriever, fga_client=fga)

    assert len(result["documents"]) == 0


def test_internal_doc_accessible_with_correct_team():
    fga = _make_fga_client(teams=["team:dev"], personal_docs=[])
    retriever = _mock_retriever([
        {"text": "팀 내부", "source": "internal.md", "sensitivity": "internal", "team_id": "team:dev"},
        {"text": "공개", "source": "public.md", "sensitivity": "public"},
    ])

    from app.graph.nodes.permission import permission_node
    from app.graph.nodes.retrieve import retrieve_node

    state = {"user_id": "u1", "question": "팀 문서", "user_teams": [], "personal_doc_ids": []}
    perm_result = permission_node(state, fga_client=fga)
    state.update(perm_result)
    result = retrieve_node(state, retriever=retriever, fga_client=fga)

    sources = [r.chunk.source for r in result["documents"]]
    assert "internal.md" in sources
    assert "public.md" in sources


def test_secret_doc_accessible_only_with_personal_doc_id():
    fga = _make_fga_client(teams=[], personal_docs=["doc:salary.md"])
    retriever = _mock_retriever([
        {"text": "급여 내역", "source": "salary.md", "sensitivity": "secret"},
    ])

    from app.graph.nodes.permission import permission_node
    from app.graph.nodes.retrieve import retrieve_node

    state = {"user_id": "u1", "question": "급여", "user_teams": [], "personal_doc_ids": []}
    perm_result = permission_node(state, fga_client=fga)
    state.update(perm_result)
    result = retrieve_node(state, retriever=retriever, fga_client=fga)

    assert len(result["documents"]) == 1
    assert result["documents"][0].chunk.source == "salary.md"


def test_secret_doc_blocked_without_personal_doc_id():
    fga = _make_fga_client(teams=[], personal_docs=[])
    retriever = _mock_retriever([
        {"text": "급여 내역", "source": "salary.md", "sensitivity": "secret"},
    ])

    from app.graph.nodes.permission import permission_node
    from app.graph.nodes.retrieve import retrieve_node

    state = {"user_id": "u1", "question": "급여", "user_teams": [], "personal_doc_ids": []}
    perm_result = permission_node(state, fga_client=fga)
    state.update(perm_result)
    result = retrieve_node(state, retriever=retriever, fga_client=fga)

    assert len(result["documents"]) == 0
