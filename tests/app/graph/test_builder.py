from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from unittest.mock import MagicMock, patch

from shared.fga.models import UserPermission
from shared.models import Answer, Chunk, SearchResult
from app.graph.builder import answer_question, build_graph


def _mock_fga_client():
    mock_fga = MagicMock()
    mock_fga.get_permission.return_value = UserPermission(user_id="anonymous", teams=[], personal_docs=[])
    mock_fga.build_chroma_filter.return_value = {"sensitivity": "public"}
    return mock_fga


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


@patch("app.graph.builder._default_fga_client")
def test_answer_question_doc_search_happy_path(mock_fga_factory):
    mock_fga_factory.return_value = _mock_fga_client()
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


@patch("app.graph.builder._default_fga_client")
def test_answer_question_doc_search_retry_on_low_grade(mock_fga_factory):
    mock_fga_factory.return_value = _mock_fga_client()
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


@patch("app.graph.builder._default_fga_client")
def test_answer_question_multi_turn_accumulates_chat_history(mock_fga_factory):
    """2턴 대화 시 chat_history가 누적되고 2턴 rewrite_query 프롬프트에 1턴 질문이 포함된다."""
    mock_fga_factory.return_value = _mock_fga_client()
    retriever = _make_retriever(text="연차는 15일", source="vacation.md")
    llm = MagicMock()
    llm.complete.side_effect = [
        # Turn 1: load_memory(pure) → rewrite → router → retrieve → grade → generate → halluc → save(pure)
        "연차 신청 방법",       # rewrite_query
        "doc_search",          # router
        "0.9",                 # grade_documents
        "연차는 15일입니다.",   # generate
        "YES",                 # check_hallucination
        # Turn 2: 동일 순서
        "연차 상세 설명",       # rewrite_query (should receive history from turn 1)
        "doc_search",          # router
        "0.9",                 # grade_documents
        "더 자세히 설명하면.", # generate
        "YES",                 # check_hallucination
    ]
    graph = build_graph(retriever=retriever, llm=llm)
    config = {"configurable": {"thread_id": "multi-turn-test-1"}}

    result1 = answer_question(graph, "연차 어떻게 써?", config=config)
    assert result1.text == "연차는 15일입니다."

    result2 = answer_question(graph, "더 자세히 알려줘", config=config)
    assert result2.text == "더 자세히 설명하면."

    # 2턴 rewrite_query 프롬프트(6번째 LLM 호출, index=5)에 1턴 질문이 있어야 함
    rewrite_prompt_turn2 = llm.complete.call_args_list[5][0][0]
    assert "연차 어떻게 써?" in rewrite_prompt_turn2


@patch("app.graph.builder._default_fga_client")
def test_answer_question_new_session_starts_with_empty_history(mock_fga_factory):
    """다른 thread_id는 이전 대화에 접근할 수 없다."""
    mock_fga_factory.return_value = _mock_fga_client()
    retriever = _make_retriever(text="문서", source="doc.md")
    llm = MagicMock()
    llm.complete.side_effect = [
        "연차 신청 방법",  # rewrite_query
        "doc_search",     # router
        "0.9",            # grade_documents
        "정답",           # generate
        "YES",            # check_hallucination
    ]
    graph = build_graph(retriever=retriever, llm=llm)
    # 새 세션 ID — 이전 대화 없음
    config = {"configurable": {"thread_id": "brand-new-session-999"}}
    result = answer_question(graph, "연차 어떻게 써?", config=config)
    assert result.text == "정답"

    # rewrite_query 프롬프트에 "없음"이 포함되어야 함 (빈 히스토리)
    rewrite_prompt = llm.complete.call_args_list[0][0][0]
    assert "없음" in rewrite_prompt
