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
    assert ref.sensitivity == "internal"
    assert ref.team_id == "team:dev"
    assert ref.document_id == "doc:1"


@pytest.mark.asyncio
async def test_generate_node_defaults_to_public_when_no_metadata():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "답변"

    state = {
        "question": "질문",
        "documents": [SearchResult(
            chunk=Chunk(text="내용", source="doc.md", chunk_id="id"), score=0.9
        )],
    }
    result = await generate_node(state, llm=mock_llm)
    ref = result["citations"][0]
    assert isinstance(ref, SourceRef)
    assert ref.sensitivity == "public"
    assert ref.team_id == ""
    assert ref.document_id == ""


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
async def test_generate_node_prepends_notice_when_no_documents():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "일반 답변"

    state = {
        "question": "질문",
        "rewritten_question": "질문",
        "documents": [],
        "relevance_score": 0.0,
        "route": "doc_search",
        "chat_history": [],
    }
    result = await generate_node(state, llm=mock_llm)

    assert result["answer"].startswith(_NOTICE_PREFIX)
    assert "일반 답변" in result["answer"]
    assert result["citations"] == []


@pytest.mark.asyncio
async def test_generate_node_prepends_notice_when_low_relevance():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "일반 답변"

    state = {
        "question": "질문",
        "rewritten_question": "질문",
        "documents": [_make_result("내용", "doc.md")],
        "relevance_score": 0.3,
        "route": "doc_search",
        "chat_history": [],
    }
    result = await generate_node(state, llm=mock_llm)

    assert result["answer"].startswith(_NOTICE_PREFIX)
    assert "일반 답변" in result["answer"]
    assert result["citations"] == []


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
async def test_generate_node_no_notice_for_web_search_route():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "웹 검색 답변"

    state = {
        "question": "질문",
        "rewritten_question": "질문",
        "documents": [],
        "relevance_score": 0.0,
        "route": "web_search",
        "chat_history": [],
    }
    result = await generate_node(state, llm=mock_llm)

    assert not result["answer"].startswith(_NOTICE_PREFIX)
    assert result["answer"] == "웹 검색 답변"


@pytest.mark.asyncio
async def test_generate_node_streams_tokens_to_queue():
    """token_queue 있을 때 llm.stream() 호출, 토큰이 큐에 쌓인다."""

    async def _fake_stream(prompt):
        for t in ["안녕", "하세요"]:
            yield t

    mock_llm = MagicMock()
    mock_llm.stream = _fake_stream

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

    tokens = []
    while not queue.empty():
        tokens.append(queue.get_nowait())

    assert tokens == [
        {"type": "token", "content": "안녕"},
        {"type": "token", "content": "하세요"},
    ]
    assert result["answer"] == "안녕하세요"
    assert len(result["citations"]) == 1


@pytest.mark.asyncio
async def test_generate_node_no_queue_uses_complete():
    """token_queue 없을 때 llm.complete() 폴백."""
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
async def test_generate_node_streams_notice_prefix_when_no_docs():
    """no-doc 경로에서 _NO_DOC_NOTICE도 토큰으로 스트리밍된다."""

    async def _fake_stream(prompt):
        yield "일반 답변"

    mock_llm = MagicMock()
    mock_llm.stream = _fake_stream

    queue: asyncio.Queue = asyncio.Queue()
    state = {
        "question": "질문",
        "rewritten_question": "질문",
        "documents": [],
        "relevance_score": 0.0,
        "route": "doc_search",
        "chat_history": [],
    }
    config = {"configurable": {"token_queue": queue}}

    result = await generate_node(state, config=config, llm=mock_llm)

    tokens = []
    while not queue.empty():
        tokens.append(queue.get_nowait()["content"])
    assert tokens[0].startswith("⚠️")   # notice prefix가 첫 토큰
    assert "일반 답변" in "".join(tokens)
    assert result["answer"].startswith("⚠️")
