import asyncio
from unittest.mock import MagicMock

import pytest

from core.models import Chunk, SearchResult, SourceRef
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


@pytest.mark.asyncio
async def test_generate_node_returns_source_refs():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "테스트 답변"

    state = {
        "question": "질문",
        "documents": [_make_result("내용", "doc.md", sensitivity="internal",
                                   team_id="team:dev", doc_id="doc:1")],
    }
    result = await generate_node(state, llm=mock_llm)

    assert result["answer"] == "테스트 답변"
    assert len(result["citations"]) == 1
    ref = result["citations"][0]
    assert isinstance(ref, SourceRef)
    assert ref.source == "doc.md"


@pytest.mark.asyncio
async def test_generate_node_citation_holds_source_only():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "답변"

    state = {
        "question": "질문",
        "documents": [SearchResult(
            chunk=Chunk(text="내용", source="hr/perf.md", chunk_id="id"), score=0.9
        )],
    }
    result = await generate_node(state, llm=mock_llm)
    ref = result["citations"][0]
    assert isinstance(ref, SourceRef)
    assert ref.source == "hr/perf.md"


@pytest.mark.asyncio
async def test_generate_node_includes_context_in_prompt():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "답변"

    state = {
        "question": "질문",
        "documents": [_make_result("중요한 내용", "doc.md")],
    }
    await generate_node(state, llm=mock_llm)

    called_prompt = mock_llm.complete.call_args[0][0]
    assert "중요한 내용" in called_prompt
    assert "질문" in called_prompt


@pytest.mark.asyncio
async def test_generate_node_uses_rewritten_question_in_prompt():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "답변"

    state = {
        "question": "원본 질문",
        "rewritten_question": "재작성된 질문",
        "documents": [_make_result("문서 내용", "doc.md")],
    }
    await generate_node(state, llm=mock_llm)

    prompt = mock_llm.complete.call_args[0][0]
    assert "재작성된 질문" in prompt
    assert "원본 질문" not in prompt


@pytest.mark.asyncio
async def test_generate_node_falls_back_to_question_when_rewritten_empty():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "답변"

    state = {
        "question": "원본 질문",
        "rewritten_question": "",
        "documents": [_make_result("내용", "doc.md")],
    }
    await generate_node(state, llm=mock_llm)

    prompt = mock_llm.complete.call_args[0][0]
    assert "원본 질문" in prompt


@pytest.mark.asyncio
async def test_generate_node_includes_chat_history_in_prompt():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "답변"

    history = [{"role": "user", "content": "이전 대화 내용"}]
    state = {
        "question": "질문",
        "rewritten_question": "재작성",
        "documents": [_make_result("문서", "doc.md")],
        "chat_history": history,
    }
    await generate_node(state, llm=mock_llm)

    prompt = mock_llm.complete.call_args[0][0]
    assert "이전 대화 내용" in prompt


_NOTICE_PREFIX = "⚠️ 관련 사내 문서를 찾지 못했습니다."


@pytest.mark.asyncio
async def test_generate_node_returns_only_notice_when_no_documents():
    mock_llm = MagicMock()

    state = {
        "question": "질문",
        "rewritten_question": "질문",
        "documents": [],
        "relevance_score": 0.0,
        "route": "doc_search",
        "chat_history": [],
    }
    result = await generate_node(state, llm=mock_llm)

    assert result["answer"] == _NOTICE_PREFIX
    assert result["citations"] == []
    mock_llm.complete.assert_not_called()


@pytest.mark.asyncio
async def test_generate_node_returns_only_notice_when_low_relevance():
    mock_llm = MagicMock()

    state = {
        "question": "질문",
        "rewritten_question": "질문",
        "documents": [_make_result("내용", "doc.md")],
        "relevance_score": 0.3,
        "route": "doc_search",
        "chat_history": [],
    }
    result = await generate_node(state, llm=mock_llm)

    assert result["answer"] == _NOTICE_PREFIX
    assert result["citations"] == []
    mock_llm.complete.assert_not_called()


@pytest.mark.asyncio
async def test_generate_node_no_notice_when_relevant_docs_exist():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "문서 기반 답변"

    state = {
        "question": "질문",
        "rewritten_question": "질문",
        "documents": [_make_result("내용", "doc.md")],
        "relevance_score": 0.8,
        "route": "doc_search",
        "chat_history": [],
    }
    result = await generate_node(state, llm=mock_llm)

    assert not result["answer"].startswith(_NOTICE_PREFIX)
    assert result["answer"] == "문서 기반 답변"
    assert len(result["citations"]) == 1


@pytest.mark.asyncio
async def test_generate_node_no_notice_for_agent_route():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "도구 실행 답변"

    state = {
        "question": "질문",
        "rewritten_question": "질문",
        "documents": [],
        "relevance_score": 0.0,
        "route": "agent",
        "chat_history": [],
    }
    result = await generate_node(state, llm=mock_llm)

    assert not result["answer"].startswith(_NOTICE_PREFIX)
    assert result["answer"] == "도구 실행 답변"


@pytest.mark.asyncio
async def test_generate_node_no_queue_uses_complete():
    """token_queue 존재 여부와 무관하게 llm.complete()를 사용한다."""
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "complete 답변"

    state = {
        "question": "질문",
        "rewritten_question": "질문",
        "documents": [_make_result("내용", "doc.md")],
        "relevance_score": 0.9,
        "route": "doc_search",
        "chat_history": [],
    }

    result = await generate_node(state, llm=mock_llm)

    mock_llm.complete.assert_called_once()
    assert result["answer"] == "complete 답변"


@pytest.mark.asyncio
async def test_generate_node_never_streams_to_queue():
    """token_queue가 있어도 큐에 흘리지 않고 complete만 쓴다 (스트리밍은 stream_answer 담당)."""
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "최종 답변"
    mock_llm.stream = MagicMock(side_effect=AssertionError("stream을 호출하면 안 된다"))

    queue: asyncio.Queue = asyncio.Queue()
    state = {
        "question": "질문",
        "rewritten_question": "질문",
        "documents": [_make_result("내용", "doc.md")],
        "relevance_score": 0.9,
        "route": "doc_search",
        "chat_history": [],
    }
    config = {"configurable": {"token_queue": queue}}

    result = await generate_node(state, config=config, llm=mock_llm)

    assert result["answer"] == "최종 답변"
    assert queue.empty()
    mock_llm.complete.assert_called_once()
