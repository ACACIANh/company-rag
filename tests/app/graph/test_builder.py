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
