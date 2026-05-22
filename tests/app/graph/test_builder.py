from unittest.mock import MagicMock

from shared.models import Answer, Chunk, SearchResult
from app.graph.builder import answer_question, build_graph


def _make_retriever(text: str = "문서", source: str = "doc.md"):
    mock = MagicMock()
    mock.retrieve.return_value = [
        SearchResult(chunk=Chunk(text=text, source=source, chunk_id="c1"), score=0.9)
    ]
    return mock


def test_build_graph_returns_compiled_graph():
    from langgraph.graph.state import CompiledStateGraph
    retriever = _make_retriever()
    llm = MagicMock()
    llm.complete.return_value = "답변"
    graph = build_graph(retriever=retriever, llm=llm)
    assert isinstance(graph, CompiledStateGraph)


def test_answer_question_returns_answer():
    retriever = _make_retriever(text="내용", source="s.md")
    llm = MagicMock()
    llm.complete.return_value = "정답"
    graph = build_graph(retriever=retriever, llm=llm)

    result = answer_question(graph, "테스트 질문")

    assert isinstance(result, Answer)
    assert result.text == "정답"
    assert result.sources == ["s.md"]


def test_answer_question_self_rag_happy_path():
    """rewrite → retrieve → grade(pass) → generate → hallucination(pass) → END"""
    retriever = _make_retriever(text="연차는 15일입니다.", source="vacation.md")
    llm = MagicMock()
    llm.complete.side_effect = [
        "연차 신청 방법",   # rewrite_query
        "0.9",             # grade_documents
        "정답",            # generate
        "YES",             # check_hallucination
    ]
    graph = build_graph(retriever=retriever, llm=llm)
    result = answer_question(graph, "연차 어떻게 써?")

    assert result.text == "정답"
    assert "vacation.md" in result.sources


def test_answer_question_retries_on_low_grade_then_passes():
    """grade(fail) → increment_retry → rewrite → retrieve → grade(pass) → generate → hallucination(pass)"""
    retriever = _make_retriever(text="내용", source="doc.md")
    llm = MagicMock()
    llm.complete.side_effect = [
        "첫 재작성",        # rewrite_query (initial)
        "0.2",              # grade_documents (fail → rewrite_retry)
        "두 번째 재작성",   # rewrite_query (retry)
        "0.8",              # grade_documents (pass → generate)
        "좋은 답변",        # generate
        "YES",              # check_hallucination
    ]
    graph = build_graph(retriever=retriever, llm=llm)
    result = answer_question(graph, "원본 질문")

    assert result.text == "좋은 답변"


def test_answer_question_retries_generate_on_hallucination_fail():
    """hallucination(fail) → generate → hallucination(pass) → END"""
    retriever = _make_retriever(text="문서", source="doc.md")
    llm = MagicMock()
    llm.complete.side_effect = [
        "재작성",        # rewrite_query
        "0.9",           # grade_documents (pass)
        "첫 답변",       # generate (hallucination will fail)
        "NO",            # check_hallucination (fail → retry generate)
        "두 번째 답변",  # generate (retry)
        "YES",           # check_hallucination (pass)
    ]
    graph = build_graph(retriever=retriever, llm=llm)
    result = answer_question(graph, "질문")

    assert result.text == "두 번째 답변"
