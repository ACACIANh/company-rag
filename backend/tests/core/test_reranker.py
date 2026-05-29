from core.models import Chunk, SearchResult
from core.reranker import NoOpReranker
from core.reranker.base import Reranker


def _sr(source: str, score: float) -> SearchResult:
    return SearchResult(
        chunk=Chunk(text="t", source=source, chunk_id=source), score=score
    )


def test_noop_implements_abc():
    assert issubclass(NoOpReranker, Reranker)


def test_noop_preserves_order():
    results = [_sr("a", 0.9), _sr("b", 0.8), _sr("c", 0.7)]
    out = NoOpReranker().rerank("q", results)
    assert [r.chunk.source for r in out] == ["a", "b", "c"]


def test_noop_truncates_to_top_k():
    results = [_sr(s, 0.5) for s in ["a", "b", "c", "d"]]
    out = NoOpReranker().rerank("q", results, top_k=2)
    assert [r.chunk.source for r in out] == ["a", "b"]


def test_noop_top_k_none_returns_all():
    results = [_sr(s, 0.5) for s in ["a", "b", "c"]]
    out = NoOpReranker().rerank("q", results, top_k=None)
    assert len(out) == 3


def test_noop_empty_input():
    assert NoOpReranker().rerank("q", []) == []
