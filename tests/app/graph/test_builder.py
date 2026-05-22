from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from unittest.mock import MagicMock

from shared.models import Answer, Chunk, SearchResult
from app.graph.builder import answer_question, build_graph


def _make_retriever(text: str = "문서", source: str = "doc.md"):
    mock = MagicMock()
    mock.retrieve.return_value = [
        SearchResult(chunk=Chunk(text=text, source=source, chunk_id=source), score=0.9)
    ]
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
    }


def test_build_graph_returns_compiled_graph():
    retriever = _make_retriever()
    llm = MagicMock()
    llm.complete.side_effect = ["재작성", "doc_search", "0.9", "답변", "YES"]
    graph = build_graph(retriever=retriever, llm=llm)
    assert isinstance(graph, CompiledStateGraph)


def test_answer_question_doc_search_happy_path():
    retriever = _make_retriever(text="연차는 15일입니다.", source="vacation.md")
    llm = MagicMock()
    llm.complete.side_effect = [
        "연차 신청 방법",  # rewrite_query
        "doc_search",     # router
        "0.9",            # grade_documents
        "정답",           # generate
        "YES",            # check_hallucination
    ]
    graph = build_graph(retriever=retriever, llm=llm)
    result = answer_question(graph, "연차 어떻게 써?")

    assert isinstance(result, Answer)
    assert result.text == "정답"
    assert "vacation.md" in result.sources


def test_answer_question_web_search_path():
    doc_retriever = _make_retriever(text="사내 문서", source="doc.md")
    web_retriever = _make_retriever(text="LangGraph 최신 기능", source="https://langchain.com")
    llm = MagicMock()
    llm.complete.side_effect = [
        "LangGraph 최신 업데이트",  # rewrite_query
        "web_search",               # router
        "웹 검색 기반 답변",         # generate
        "YES",                      # check_hallucination
    ]
    graph = build_graph(retriever=doc_retriever, llm=llm, web_search_retriever=web_retriever)
    result = answer_question(graph, "LangGraph 최신 버전 알려줘")

    assert result.text == "웹 검색 기반 답변"
    assert "https://langchain.com" in result.sources


def test_answer_question_doc_search_retry_on_low_grade():
    retriever = _make_retriever(text="내용", source="doc.md")
    llm = MagicMock()
    llm.complete.side_effect = [
        "첫 재작성",        # rewrite_query (initial)
        "doc_search",      # router (initial)
        "0.2",             # grade (fail → rewrite_retry)
        "두 번째 재작성",   # rewrite_query (retry)
        "doc_search",      # router (retry — rewrite → router → retrieve)
        "0.8",             # grade (pass)
        "좋은 답변",        # generate
        "YES",             # check_hallucination
    ]
    graph = build_graph(retriever=retriever, llm=llm)
    result = answer_question(graph, "원본 질문")

    assert result.text == "좋은 답변"


def test_tool_call_triggers_interrupt():
    """LangGraph 1.2.x: invoke() returns __interrupt__ key instead of raising GraphInterrupt."""
    doc_retriever = _make_retriever()
    web_retriever = _make_retriever()
    llm = MagicMock()
    llm.complete.side_effect = [
        "회의실 예약 요청",  # rewrite_query
        "tool_call",        # router
    ]
    graph = build_graph(retriever=doc_retriever, llm=llm, web_search_retriever=web_retriever)
    config = {"configurable": {"thread_id": "test-interrupt-1"}}

    result = graph.invoke(_make_initial_state("회의실 예약해줘"), config=config)
    assert "__interrupt__" in result
    assert len(result["__interrupt__"]) > 0


def test_tool_call_completes_after_user_approves():
    """LangGraph 1.2.x: resume with Command(resume=True) after __interrupt__ state."""
    doc_retriever = _make_retriever()
    web_retriever = _make_retriever()
    llm = MagicMock()
    llm.complete.side_effect = [
        "회의실 예약 요청",     # rewrite_query
        "tool_call",            # router
        "Mock 실행 결과 답변",  # generate
        "YES",                  # check_hallucination
    ]
    graph = build_graph(retriever=doc_retriever, llm=llm, web_search_retriever=web_retriever)
    config = {"configurable": {"thread_id": "test-interrupt-2"}}

    result = graph.invoke(_make_initial_state("회의실 예약해줘"), config=config)
    assert "__interrupt__" in result

    final = graph.invoke(Command(resume=True), config=config)
    assert final["answer"] == "Mock 실행 결과 답변"


def test_tool_call_ends_when_user_denies():
    """LangGraph 1.2.x: resume with Command(resume=False) skips tool execution."""
    doc_retriever = _make_retriever()
    web_retriever = _make_retriever()
    llm = MagicMock()
    llm.complete.side_effect = [
        "슬랙 메시지 요청",  # rewrite_query
        "tool_call",         # router
    ]
    graph = build_graph(retriever=doc_retriever, llm=llm, web_search_retriever=web_retriever)
    config = {"configurable": {"thread_id": "test-interrupt-3"}}

    result = graph.invoke(_make_initial_state("팀에 공지 보내줘"), config=config)
    assert "__interrupt__" in result

    final = graph.invoke(Command(resume=False), config=config)
    assert final["answer"] == ""
