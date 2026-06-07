import pytest
from unittest.mock import AsyncMock, MagicMock
from core.models import Chunk, SearchResult
from app.graph.nodes.retrieve import retrieve_node


def _make_result(text="내용", source="doc.md") -> SearchResult:
    return SearchResult(chunk=Chunk(text=text, source=source, chunk_id="test-1"), score=0.9)


def _mock_fga(teams=None):
    client = MagicMock()
    if not teams:
        client.build_pg_filter.return_value = ("sensitivity = 'public'", [])
    else:
        client.build_pg_filter.return_value = (
            "sensitivity = 'public' OR (team_id = ANY($1) AND sensitivity = 'internal')",
            [teams],
        )
    return client


@pytest.mark.asyncio
async def test_retrieve_node_returns_documents():
    mock_retriever = MagicMock()
    mock_retriever.retrieve = AsyncMock(return_value=[_make_result()])
    mock_fga = _mock_fga()
    state = {"question": "테스트", "user_id": "u1", "user_teams": [], "personal_doc_ids": []}
    result = await retrieve_node(state, retriever=mock_retriever, fga_client=mock_fga)
    assert "documents" in result
    assert len(result["documents"]) == 1


@pytest.mark.asyncio
async def test_retrieve_node_uses_rewritten_question():
    mock_retriever = MagicMock()
    mock_retriever.retrieve = AsyncMock(return_value=[])
    mock_fga = _mock_fga()
    await retrieve_node(
        {"question": "원본", "rewritten_question": "재작성", "user_id": "u1",
         "user_teams": [], "personal_doc_ids": []},
        retriever=mock_retriever, fga_client=mock_fga,
    )
    assert mock_retriever.retrieve.call_args[0][0] == "재작성"


@pytest.mark.asyncio
async def test_retrieve_node_passes_pg_filter():
    mock_retriever = MagicMock()
    mock_retriever.retrieve = AsyncMock(return_value=[])
    mock_fga = _mock_fga(teams=["team:dev"])
    mock_fga.build_pg_filter.return_value = ("sensitivity = 'public'", [])
    await retrieve_node(
        {"question": "q", "user_id": "u1", "user_teams": ["team:dev"], "personal_doc_ids": []},
        retriever=mock_retriever, fga_client=mock_fga,
    )
    _, kwargs = mock_retriever.retrieve.call_args
    assert "where_clause" in kwargs
    assert "params" in kwargs


@pytest.mark.asyncio
async def test_retrieve_node_falls_back_to_question():
    mock_retriever = MagicMock()
    mock_retriever.retrieve = AsyncMock(return_value=[])
    mock_fga = _mock_fga()
    await retrieve_node(
        {"question": "원본", "rewritten_question": "", "user_id": "u1",
         "user_teams": [], "personal_doc_ids": []},
        retriever=mock_retriever, fga_client=mock_fga,
    )
    assert mock_retriever.retrieve.call_args[0][0] == "원본"


@pytest.mark.asyncio
async def test_retrieve_node_multi_query_uses_retrieve_batch():
    """multi_query는 임베딩을 묶기 위해 retrieve_batch를 쿼리 전체로 1회 호출한다."""
    mock_retriever = MagicMock()
    mock_retriever.retrieve_batch = AsyncMock(return_value=[[], [], []])
    mock_fga = _mock_fga()

    state = {
        "question": "원본",
        "rewritten_question": "재작성",
        "multi_queries": ["쿼리1", "쿼리2", "쿼리3"],
        "user_id": "u1",
        "user_teams": [],
        "personal_doc_ids": [],
    }
    await retrieve_node(state, retriever=mock_retriever, fga_client=mock_fga)

    mock_retriever.retrieve_batch.assert_called_once()
    assert mock_retriever.retrieve_batch.call_args[0][0] == ["쿼리1", "쿼리2", "쿼리3"]


@pytest.mark.asyncio
async def test_retrieve_node_multi_query_merges_results_via_rrf():
    from core.models import Chunk

    def _sr(cid: str) -> SearchResult:
        return SearchResult(chunk=Chunk(text="t", source=cid, chunk_id=cid), score=0.9)

    mock_retriever = MagicMock()
    # q1 → [a, b], q2 → [b, c]: b는 양쪽에 등장 → RRF 점수 높음
    mock_retriever.retrieve_batch = AsyncMock(return_value=[
        [_sr("a"), _sr("b")],
        [_sr("b"), _sr("c")],
    ])
    mock_fga = _mock_fga()

    state = {
        "question": "원본",
        "rewritten_question": "재작성",
        "multi_queries": ["쿼리1", "쿼리2"],
        "user_id": "u1",
        "user_teams": [],
        "personal_doc_ids": [],
    }
    result = await retrieve_node(state, retriever=mock_retriever, fga_client=mock_fga, top_k=10)
    chunk_ids = [r.chunk.chunk_id for r in result["documents"]]
    # b는 두 리스트 모두에 등장하므로 RRF 상위 순위여야 함
    assert chunk_ids[0] == "b"


@pytest.mark.asyncio
async def test_retrieve_node_without_reranker_truncates_to_top_k():
    """reranker 미주입(None)이면 reranking 없이 상위 top_k만 순서 보존해 반환(identity)."""
    def _sr(cid: str) -> SearchResult:
        return SearchResult(chunk=Chunk(text="t", source=cid, chunk_id=cid), score=0.9)

    mock_retriever = MagicMock()
    mock_retriever.retrieve = AsyncMock(return_value=[_sr("a"), _sr("b"), _sr("c")])
    mock_fga = _mock_fga()
    state = {"question": "q", "user_id": "u1", "user_teams": [], "personal_doc_ids": []}

    result = await retrieve_node(state, retriever=mock_retriever, fga_client=mock_fga, top_k=2)

    assert [r.chunk.chunk_id for r in result["documents"]] == ["a", "b"]


@pytest.mark.asyncio
async def test_retrieve_node_uses_injected_reranker():
    """reranker 주입 시 그 rerank 결과를 그대로 사용한다."""
    def _sr(cid: str) -> SearchResult:
        return SearchResult(chunk=Chunk(text="t", source=cid, chunk_id=cid), score=0.9)

    mock_retriever = MagicMock()
    mock_retriever.retrieve = AsyncMock(return_value=[_sr("a"), _sr("b")])
    reranked = [_sr("b"), _sr("a")]
    mock_reranker = MagicMock()
    mock_reranker.rerank = MagicMock(return_value=reranked)
    mock_fga = _mock_fga()
    state = {"question": "q", "user_id": "u1", "user_teams": [], "personal_doc_ids": []}

    result = await retrieve_node(
        state, retriever=mock_retriever, fga_client=mock_fga, reranker=mock_reranker,
    )

    mock_reranker.rerank.assert_called_once()
    assert result["documents"] == reranked


@pytest.mark.asyncio
async def test_retrieve_node_single_query_when_multi_queries_empty():
    mock_retriever = MagicMock()
    mock_retriever.retrieve = AsyncMock(return_value=[_make_result()])
    mock_fga = _mock_fga()

    state = {
        "question": "원본",
        "rewritten_question": "재작성",
        "multi_queries": [],
        "user_id": "u1",
        "user_teams": [],
        "personal_doc_ids": [],
    }
    await retrieve_node(state, retriever=mock_retriever, fga_client=mock_fga)

    assert mock_retriever.retrieve.call_count == 1
    assert mock_retriever.retrieve.call_args[0][0] == "재작성"
