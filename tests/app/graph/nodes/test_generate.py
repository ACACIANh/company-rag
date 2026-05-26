from unittest.mock import MagicMock

from shared.models import Chunk, SearchResult, SourceRef
from app.graph.nodes.generate import generate_node


def _make_result(text: str, source: str, sensitivity: str = "public",
                 team_id: str = "", doc_id: str = "") -> SearchResult:
    return SearchResult(
        chunk=Chunk(
            text=text,
            source=source,
            chunk_id="test_id",
            metadata={"sensitivity": sensitivity, "team_id": team_id, "document_id": doc_id},
        ),
        score=0.9,
    )


def test_generate_node_returns_source_refs():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "테스트 답변"

    state = {
        "question": "질문",
        "documents": [_make_result("내용", "doc.md", sensitivity="internal",
                                   team_id="team:dev", doc_id="doc:1")],
    }
    result = generate_node(state, llm=mock_llm)

    assert result["answer"] == "테스트 답변"
    assert len(result["citations"]) == 1
    ref = result["citations"][0]
    assert isinstance(ref, SourceRef)
    assert ref.source == "doc.md"
    assert ref.sensitivity == "internal"
    assert ref.team_id == "team:dev"
    assert ref.document_id == "doc:1"


def test_generate_node_defaults_to_public_when_no_metadata():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "답변"

    state = {
        "question": "질문",
        "documents": [SearchResult(
            chunk=Chunk(text="내용", source="doc.md", chunk_id="id"), score=0.9
        )],
    }
    result = generate_node(state, llm=mock_llm)
    ref = result["citations"][0]
    assert isinstance(ref, SourceRef)
    assert ref.sensitivity == "public"
    assert ref.team_id == ""
    assert ref.document_id == ""


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


def test_generate_node_uses_rewritten_question_in_prompt():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "답변"

    state = {
        "question": "원본 질문",
        "rewritten_question": "재작성된 질문",
        "documents": [_make_result("문서 내용", "doc.md")],
    }
    generate_node(state, llm=mock_llm)

    prompt = mock_llm.complete.call_args[0][0]
    assert "재작성된 질문" in prompt
    assert "원본 질문" not in prompt


def test_generate_node_falls_back_to_question_when_rewritten_empty():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "답변"

    state = {
        "question": "원본 질문",
        "rewritten_question": "",
        "documents": [_make_result("내용", "doc.md")],
    }
    generate_node(state, llm=mock_llm)

    prompt = mock_llm.complete.call_args[0][0]
    assert "원본 질문" in prompt


def test_generate_node_includes_chat_history_in_prompt():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "답변"

    history = [{"role": "user", "content": "이전 대화 내용"}]
    state = {
        "question": "질문",
        "rewritten_question": "재작성",
        "documents": [_make_result("문서", "doc.md")],
        "chat_history": history,
    }
    generate_node(state, llm=mock_llm)

    prompt = mock_llm.complete.call_args[0][0]
    assert "이전 대화 내용" in prompt
