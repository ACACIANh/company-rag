from unittest.mock import MagicMock, patch

import pytest

from shared.models import Chunk, SearchResult
from shared.reranker.llm_reranker import LLMReranker


def _sr(source: str, text: str = "내용", score: float = 0.5) -> SearchResult:
    return SearchResult(chunk=Chunk(text=text, source=source, chunk_id=source), score=score)


def _mock_client(response_text: str) -> MagicMock:
    client = MagicMock()
    choice = MagicMock()
    choice.message.content = response_text
    client.chat.completions.create.return_value = MagicMock(choices=[choice])
    return client


def test_rerank_reorders_by_llm_response():
    results = [_sr("a"), _sr("b"), _sr("c")]
    client = _mock_client("[2, 0, 1]")
    reranker = LLMReranker(client, model="gpt-4o-mini")

    out = reranker.rerank("질문", results)

    assert [r.chunk.source for r in out] == ["c", "a", "b"]


def test_rerank_applies_top_k():
    results = [_sr("a"), _sr("b"), _sr("c")]
    client = _mock_client("[2, 0, 1]")
    reranker = LLMReranker(client, model="gpt-4o-mini")

    out = reranker.rerank("질문", results, top_k=2)

    assert [r.chunk.source for r in out] == ["c", "a"]


def test_rerank_fallback_on_parse_failure():
    results = [_sr("a"), _sr("b")]
    client = _mock_client("잘못된 응답")
    reranker = LLMReranker(client, model="gpt-4o-mini")

    out = reranker.rerank("질문", results)

    assert [r.chunk.source for r in out] == ["a", "b"]


def test_rerank_fallback_on_api_error():
    results = [_sr("a"), _sr("b")]
    client = MagicMock()
    client.chat.completions.create.side_effect = RuntimeError("API 오류")
    reranker = LLMReranker(client, model="gpt-4o-mini")

    out = reranker.rerank("질문", results)

    assert [r.chunk.source for r in out] == ["a", "b"]


def test_rerank_appends_missing_indices():
    """LLM이 일부 인덱스를 빠뜨리면 원래 순서로 뒤에 추가."""
    results = [_sr("a"), _sr("b"), _sr("c")]
    client = _mock_client("[2]")
    reranker = LLMReranker(client, model="gpt-4o-mini")

    out = reranker.rerank("질문", results)

    assert out[0].chunk.source == "c"
    assert set(r.chunk.source for r in out) == {"a", "b", "c"}


def test_rerank_empty_input():
    client = _mock_client("[]")
    reranker = LLMReranker(client, model="gpt-4o-mini")

    assert reranker.rerank("질문", []) == []
