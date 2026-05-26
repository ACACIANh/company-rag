import pytest
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from unittest.mock import AsyncMock, MagicMock

from shared.fga.models import UserPermission
from shared.models import Answer, Chunk, SearchResult
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


def test_tool_call_completes_after_user_approves():
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

    result = graph.invoke(_make_initial_state("회의실 예약해줘"), config=config)
    assert "__interrupt__" in result

    final = graph.invoke(Command(resume=True), config=config)
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
