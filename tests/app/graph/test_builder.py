import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from shared.fga.models import UserPermission
from shared.models import Answer, Chunk, SearchResult, SourceRef
from app.graph.builder import answer_question, build_graph


def _mock_fga_client():
    mock_fga = MagicMock()
    mock_fga.get_permission = AsyncMock(return_value=UserPermission(
        user_id="anonymous", teams=[], personal_docs=[]
    ))
    mock_fga.build_pg_filter = MagicMock(return_value=("sensitivity = 'public'", []))
    return mock_fga


def _make_retriever(text: str = "문서", source: str = "doc.md"):
    mock = MagicMock()
    mock.retrieve = AsyncMock(return_value=[
        SearchResult(chunk=Chunk(text=text, source=source, chunk_id=source), score=0.9)
    ])
    return mock


def _make_initial_state(question: str) -> dict:
    return {
        "question": question,
        "rewritten_question": "",
        "chat_history": [],
        "route": "doc_search",
        "documents": [],
        "relevance_score": 0.0,
        "retry_count": 0,
        "answer": "",
        "citations": [],
        "hallucination_passed": False,
        "confirmed": False,
        "tool_input": "",
        "user_id": "anonymous",
        "allowed_doc_ids": [],
        "user_teams": [],
        "personal_doc_ids": [],
    }


def test_build_graph_returns_compiled_graph():
    retriever = _make_retriever()
    llm = MagicMock()
    fga_client = _mock_fga_client()
    graph = build_graph(retriever=retriever, llm=llm, fga_client=fga_client)
    assert isinstance(graph, CompiledStateGraph)


async def test_answer_question_doc_search_happy_path():
    retriever = _make_retriever(text="연차는 15일입니다.", source="vacation.md")
    llm = MagicMock()
    llm.complete.side_effect = [
        "연차 신청 방법",
        "doc_search",
        "0.9",
        "정답",
        "YES",
    ]
    graph = build_graph(retriever=retriever, llm=llm, fga_client=_mock_fga_client())
    result = await answer_question(graph, "연차 어떻게 써?")

    assert isinstance(result, Answer)
    assert result.text == "정답"
    assert any(ref.source == "vacation.md" for ref in result.sources)


async def test_answer_question_web_search_path():
    doc_retriever = _make_retriever(text="사내 문서", source="doc.md")
    web_retriever = _make_retriever(text="LangGraph 최신 기능", source="https://langchain.com")
    llm = MagicMock()
    llm.complete.side_effect = [
        "LangGraph 최신 업데이트",
        "web_search",
        "웹 검색 기반 답변",
        "YES",
    ]
    graph = build_graph(
        retriever=doc_retriever, llm=llm, fga_client=_mock_fga_client(),
        web_search_retriever=web_retriever,
    )
    result = await answer_question(graph, "LangGraph 최신 버전 알려줘")

    assert result.text == "웹 검색 기반 답변"
    assert any(ref.source == "https://langchain.com" for ref in result.sources)


async def test_answer_question_doc_search_retry_on_low_grade():
    retriever = _make_retriever(text="내용", source="doc.md")
    llm = MagicMock()
    llm.complete.side_effect = [
        "첫 재작성",
        "doc_search",
        "0.2",
        "두 번째 재작성",
        "doc_search",
        "0.8",
        "좋은 답변",
        "YES",
    ]
    graph = build_graph(retriever=retriever, llm=llm, fga_client=_mock_fga_client())
    result = await answer_question(graph, "원본 질문")

    assert result.text == "좋은 답변"


def test_tool_call_triggers_interrupt():
    """LangGraph: invoke() returns __interrupt__ key when HITL interrupt fires."""
    doc_retriever = _make_retriever()
    web_retriever = _make_retriever()
    llm = MagicMock()
    llm.complete.side_effect = [
        "회의실 예약 요청",
        "tool_call",
    ]
    graph = build_graph(
        retriever=doc_retriever, llm=llm, fga_client=_mock_fga_client(),
        web_search_retriever=web_retriever,
    )
    config = {"configurable": {"thread_id": "test-interrupt-1"}}

    result = graph.invoke(_make_initial_state("회의실 예약해줘"), config=config)
    assert "__interrupt__" in result
    assert len(result["__interrupt__"]) > 0


@pytest.mark.asyncio
async def test_tool_call_completes_after_user_approves():
    doc_retriever = _make_retriever()
    web_retriever = _make_retriever()
    llm = MagicMock()
    llm.complete.side_effect = [
        "회의실 예약 요청",
        "tool_call",
        "Mock 실행 결과 답변",
        "YES",
    ]
    graph = build_graph(
        retriever=doc_retriever, llm=llm, fga_client=_mock_fga_client(),
        web_search_retriever=web_retriever,
    )
    config = {"configurable": {"thread_id": "test-interrupt-2"}}

    result = await graph.ainvoke(_make_initial_state("회의실 예약해줘"), config=config)
    assert "__interrupt__" in result

    final = await graph.ainvoke(Command(resume=True), config=config)
    assert final["answer"] == "Mock 실행 결과 답변"


def test_tool_call_ends_when_user_denies():
    doc_retriever = _make_retriever()
    web_retriever = _make_retriever()
    llm = MagicMock()
    llm.complete.side_effect = [
        "슬랙 메시지 요청",
        "tool_call",
    ]
    graph = build_graph(
        retriever=doc_retriever, llm=llm, fga_client=_mock_fga_client(),
        web_search_retriever=web_retriever,
    )
    config = {"configurable": {"thread_id": "test-interrupt-3"}}

    result = graph.invoke(_make_initial_state("팀에 공지 보내줘"), config=config)
    assert "__interrupt__" in result

    final = graph.invoke(Command(resume=False), config=config)
    assert final["answer"] == ""


async def test_answer_question_multi_turn_accumulates_chat_history():
    retriever = _make_retriever(text="연차는 15일", source="vacation.md")
    llm = MagicMock()
    llm.complete.side_effect = [
        "연차 신청 방법",
        "doc_search",
        "0.9",
        "연차는 15일입니다.",
        "YES",
        "연차 상세 설명",
        "doc_search",
        "0.9",
        "더 자세히 설명하면.",
        "YES",
    ]
    graph = build_graph(retriever=retriever, llm=llm, fga_client=_mock_fga_client())
    config = {"configurable": {"thread_id": "multi-turn-test-1"}}

    result1 = await answer_question(graph, "연차 어떻게 써?", config=config)
    assert result1.text == "연차는 15일입니다."

    result2 = await answer_question(graph, "더 자세히 알려줘", config=config)
    assert result2.text == "더 자세히 설명하면."

    rewrite_prompt_turn2 = llm.complete.call_args_list[5][0][0]
    assert "연차 어떻게 써?" in rewrite_prompt_turn2


async def test_answer_question_new_session_starts_with_empty_history():
    retriever = _make_retriever(text="문서", source="doc.md")
    llm = MagicMock()
    llm.complete.side_effect = [
        "연차 신청 방법",
        "doc_search",
        "0.9",
        "정답",
        "YES",
    ]
    graph = build_graph(retriever=retriever, llm=llm, fga_client=_mock_fga_client())
    config = {"configurable": {"thread_id": "brand-new-session-999"}}
    result = await answer_question(graph, "연차 어떻게 써?", config=config)
    assert result.text == "정답"

    rewrite_prompt = llm.complete.call_args_list[0][0][0]
    assert "없음" in rewrite_prompt


@pytest.mark.asyncio
async def test_stream_answer_puts_tokens_and_done_in_queue():
    """stream_answer가 토큰→sources→done 순서로 큐에 넣는다."""
    from app.graph.builder import stream_answer

    mock_final = {
        "answer": "안녕하세요",
        "citations": [SourceRef(source="doc.md")],
    }
    mock_graph = MagicMock()
    mock_graph.aget_state = AsyncMock(return_value=MagicMock(values={}))
    mock_graph.ainvoke = AsyncMock(return_value=mock_final)

    mock_store = AsyncMock()
    queue: asyncio.Queue = asyncio.Queue()

    await stream_answer(
        graph=mock_graph,
        question="질문",
        config={"configurable": {"thread_id": "t1"}},
        user_id="alice",
        allowed_doc_ids=[],
        token_queue=queue,
        session_store=mock_store,
        session_id="sess-1",
        is_new_session=True,
    )

    events = []
    while not queue.empty():
        events.append(queue.get_nowait())

    types = [e["type"] for e in events]
    assert "sources" in types
    assert types[-1] == "done"
    done_event = events[-1]
    assert done_event["session_id"] == "sess-1"

    sources_event = next(e for e in events if e["type"] == "sources")
    assert sources_event["sources"] == ["doc.md"]


@pytest.mark.asyncio
async def test_stream_answer_puts_error_then_done_on_exception():
    """graph.ainvoke 예외 시 error→done 순서로 큐에 넣는다."""
    from app.graph.builder import stream_answer

    mock_graph = MagicMock()
    mock_graph.aget_state = AsyncMock(return_value=MagicMock(values={}))
    mock_graph.ainvoke = AsyncMock(side_effect=RuntimeError("LLM 오류"))

    mock_store = AsyncMock()
    queue: asyncio.Queue = asyncio.Queue()

    await stream_answer(
        graph=mock_graph,
        question="질문",
        config={"configurable": {"thread_id": "t1"}},
        user_id="alice",
        allowed_doc_ids=[],
        token_queue=queue,
        session_store=mock_store,
        session_id="sess-1",
        is_new_session=False,
    )

    events = []
    while not queue.empty():
        events.append(queue.get_nowait())

    assert events[0]["type"] == "error"
    assert "LLM 오류" in events[0]["message"]
    assert events[1]["type"] == "done"


@pytest.mark.asyncio
async def test_answer_question_uses_chat_history_fallback():
    """checkpointer가 비어있어도 chat_history_fallback이 프롬프트에 사용된다."""
    retriever = _make_retriever(text="연차는 15일", source="vacation.md")
    llm = MagicMock()
    llm.complete.side_effect = [
        "연차 추가 질문",
        "doc_search",
        "0.9",
        "추가 답변",
        "YES",
    ]
    graph = build_graph(retriever=retriever, llm=llm, fga_client=_mock_fga_client())
    config = {"configurable": {"thread_id": "fallback-test-unique-1"}}

    fallback = [
        {"role": "user", "content": "연차 어떻게 써?"},
        {"role": "assistant", "content": "연차는 15일입니다."},
    ]
    result = await answer_question(
        graph, "더 자세히 알려줘", config=config, chat_history_fallback=fallback
    )
    assert result.text == "추가 답변"
    rewrite_prompt = llm.complete.call_args_list[0][0][0]
    assert "연차 어떻게 써?" in rewrite_prompt


@pytest.mark.asyncio
async def test_stream_answer_falls_back_to_session_store_history():
    """checkpointer 비어있고 기존 세션이면 session_store 메시지를 chat_history로 사용한다."""
    from app.graph.builder import stream_answer
    from shared.session.base import StoredMessage

    captured: dict = {}
    mock_final = {"answer": "답변", "citations": []}
    mock_graph = MagicMock()
    mock_graph.aget_state = AsyncMock(return_value=MagicMock(values={}))

    async def capture_ainvoke(initial, config=None):
        captured["chat_history"] = initial.get("chat_history", [])
        return mock_final

    mock_graph.ainvoke = capture_ainvoke

    mock_store = AsyncMock()
    mock_store.get_messages = AsyncMock(return_value=[
        StoredMessage(role="user", content="이전 질문", sources=[]),
        StoredMessage(role="assistant", content="이전 답변", sources=[]),
    ])

    queue: asyncio.Queue = asyncio.Queue()
    await stream_answer(
        graph=mock_graph,
        question="후속 질문",
        config={"configurable": {"thread_id": "t-fallback"}},
        user_id="alice",
        allowed_doc_ids=[],
        token_queue=queue,
        session_store=mock_store,
        session_id="sess-fallback",
        is_new_session=False,
    )

    assert captured["chat_history"] == [
        {"role": "user", "content": "이전 질문"},
        {"role": "assistant", "content": "이전 답변"},
    ]


@pytest.mark.asyncio
async def test_stream_answer_does_not_load_store_for_new_session():
    """새 세션이면 session_store.get_messages를 호출하지 않는다."""
    from app.graph.builder import stream_answer

    mock_final = {"answer": "답변", "citations": []}
    mock_graph = MagicMock()
    mock_graph.aget_state = AsyncMock(return_value=MagicMock(values={}))
    mock_graph.ainvoke = AsyncMock(return_value=mock_final)

    mock_store = AsyncMock()
    mock_store.get_messages = AsyncMock(return_value=[])

    queue: asyncio.Queue = asyncio.Queue()
    await stream_answer(
        graph=mock_graph,
        question="첫 질문",
        config={"configurable": {"thread_id": "t-new"}},
        user_id="alice",
        allowed_doc_ids=[],
        token_queue=queue,
        session_store=mock_store,
        session_id="sess-new",
        is_new_session=True,
    )

    mock_store.get_messages.assert_not_called()


@pytest.mark.asyncio
async def test_stream_answer_saves_session():
    """완료 후 session_store에 user/assistant 메시지를 기록한다."""
    from app.graph.builder import stream_answer

    mock_final = {"answer": "답변", "citations": []}
    mock_graph = MagicMock()
    mock_graph.aget_state = AsyncMock(return_value=MagicMock(values={}))
    mock_graph.ainvoke = AsyncMock(return_value=mock_final)

    mock_store = AsyncMock()
    queue: asyncio.Queue = asyncio.Queue()

    await stream_answer(
        graph=mock_graph,
        question="안녕",
        config={"configurable": {"thread_id": "t1"}},
        user_id="alice",
        allowed_doc_ids=[],
        token_queue=queue,
        session_store=mock_store,
        session_id="sess-2",
        is_new_session=True,
    )

    mock_store.create_session.assert_called_once_with("sess-2", "alice", "안녕")
    assert mock_store.add_message.call_count == 2
