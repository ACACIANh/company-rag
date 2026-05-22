from unittest.mock import MagicMock

from shared.models import Chunk, SearchResult
from app.graph.nodes.generate import generate_node


def _make_result(text: str, source: str) -> SearchResult:
    return SearchResult(chunk=Chunk(text=text, source=source, chunk_id="test_id"), score=0.9)


def test_generate_node_returns_answer_and_citations():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "테스트 답변"

    state = {
        "question": "질문",
        "documents": [_make_result("문서 내용", "source.md")],
    }
    result = generate_node(state, llm=mock_llm)

    assert result["answer"] == "테스트 답변"
    assert result["citations"] == ["source.md"]


def test_generate_node_includes_context_in_prompt():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "답변"

    state = {
        "question": "질문",
        "documents": [_make_result("중요한 내용", "doc.md")],
    }
    generate_node(state, llm=mock_llm)

    called_prompt = mock_llm.complete.call_args[0][0]
    assert "중요한 내용" in called_prompt
    assert "질문" in called_prompt
