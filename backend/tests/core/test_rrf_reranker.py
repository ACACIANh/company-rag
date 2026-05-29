from unittest.mock import MagicMock

from core.models import Chunk, SearchResult
from core.reranker.rrf_reranker import RRFReranker


def _sr(chunk_id: str, score: float = 0.5) -> SearchResult:
    return SearchResult(
        chunk=Chunk(text="t", source=chunk_id, chunk_id=chunk_id), score=score
    )


def _retriever(results: list[SearchResult]) -> MagicMock:
    r = MagicMock()
    r.retrieve.return_value = results
    return r


def test_rrf_fuses_two_lists():
    # primary: [a(1위), b(2위)]  secondary: [b(1위), a(2위)]
    # a: 1/61 + 1/62 ≈ 0.02783
    # b: 1/62 + 1/61 ≈ 0.02783  → 동점이면 primary 순서 유지 (dict 삽입 순)
    primary = [_sr("a"), _sr("b")]
    reranker = RRFReranker(_retriever([_sr("b"), _sr("a")]), k=60)
    out = reranker.rerank("q", primary)
    assert set(r.chunk.chunk_id for r in out) == {"a", "b"}


def test_rrf_promotes_doc_in_both_lists():
    # c는 primary 3위, secondary 1위 → RRF 점수 높아짐
    primary = [_sr("a"), _sr("b"), _sr("c")]
    secondary = [_sr("c"), _sr("d")]
    reranker = RRFReranker(_retriever(secondary), k=60)
    out = reranker.rerank("q", primary)
    # c는 양쪽에 등장하므로 점수가 가장 높아야 함
    assert out[0].chunk.chunk_id == "c"


def test_rrf_includes_secondary_only_docs():
    primary = [_sr("a")]
    secondary = [_sr("b")]
    reranker = RRFReranker(_retriever(secondary), k=60)
    out = reranker.rerank("q", primary)
    assert {r.chunk.chunk_id for r in out} == {"a", "b"}


def test_rrf_top_k_truncates():
    primary = [_sr("a"), _sr("b"), _sr("c")]
    reranker = RRFReranker(_retriever([]), k=60)
    out = reranker.rerank("q", primary, top_k=2)
    assert len(out) == 2


def test_rrf_empty_primary():
    reranker = RRFReranker(_retriever([_sr("a")]), k=60)
    out = reranker.rerank("q", [])
    assert out[0].chunk.chunk_id == "a"


def test_rrf_empty_both():
    reranker = RRFReranker(_retriever([]), k=60)
    assert reranker.rerank("q", []) == []
