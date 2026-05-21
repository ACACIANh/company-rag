from unittest.mock import MagicMock, patch

from shared.models import Answer, Chunk, SearchResult


def _make_result(source: str, text: str = "text") -> SearchResult:
    return SearchResult(
        chunk=Chunk(text=text, source=source, chunk_id=source), score=0.9
    )


def test_pipeline_qa_end_to_end():
    fake_retriever = MagicMock()
    fake_retriever.retrieve.return_value = [
        _make_result("a.md", "연차 15일"),
        _make_result("a.md", "연차 사용법"),  # 같은 source 두 개
        _make_result("b.md", "휴가 정책"),
    ]
    fake_reranker = MagicMock()
    fake_reranker.rerank.side_effect = lambda q, r, top_k=None: r[: (top_k or len(r))]
    fake_llm = MagicMock()
    fake_llm.complete.return_value = "연차는 15일입니다."

    from workflows.pipeline import qa as qa_mod

    with patch.object(qa_mod, "_get_components") as get:
        get.return_value = (fake_retriever, fake_reranker, fake_llm)
        ans: Answer = qa_mod.run("연차 며칠?")

    assert ans.text == "연차는 15일입니다."
    # sources deduped
    assert sorted(ans.sources) == ["a.md", "b.md"]
    # trace contains 3 step names
    names = [s["name"] for s in ans.trace or []]
    assert names == ["retrieve", "rerank", "generate"]
