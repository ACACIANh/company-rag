from langchain_core.messages import AIMessage, HumanMessage

from shared.llm.base import LLMClient
from shared.models import Chunk, SearchResult
from shared.retriever.base import Retriever

from graphs.rag_basic import build_graph, generate_node, retrieve_node


class FakeRetriever(Retriever):
    def __init__(self, results: list[SearchResult]) -> None:
        self._results = results
        self.last_query: str | None = None
        self.last_top_k: int | None = None

    def retrieve(self, query: str, top_k: int = 5) -> list[SearchResult]:
        self.last_query = query
        self.last_top_k = top_k
        return self._results


class FakeLLM(LLMClient):
    def __init__(self, response: str = "fake answer") -> None:
        self._response = response
        self.last_prompt: str | None = None

    def complete(self, prompt: str) -> str:
        self.last_prompt = prompt
        return self._response


def _sr(text: str, source: str, chunk_id: str = "c1", score: float = 0.9) -> SearchResult:
    return SearchResult(
        chunk=Chunk(text=text, source=source, chunk_id=chunk_id),
        score=score,
    )


def test_retrieve_node_calls_retriever_with_last_message():
    fake = FakeRetriever([_sr("hello", "s.md")])
    state = {"messages": [HumanMessage(content="question?")]}

    result = retrieve_node(state, retriever=fake)

    assert fake.last_query == "question?"
    assert fake.last_top_k == 5
    assert len(result["retrieved_docs"]) == 1
    assert result["retrieved_docs"][0].chunk.source == "s.md"


def test_generate_node_appends_aimessage_with_context():
    fake = FakeLLM(response="final answer")
    docs = [_sr("context-text", "s.md")]
    state = {
        "messages": [HumanMessage(content="question?")],
        "retrieved_docs": docs,
    }

    result = generate_node(state, llm=fake)

    assert "context-text" in fake.last_prompt
    assert "question?" in fake.last_prompt
    assert len(result["messages"]) == 1
    assert isinstance(result["messages"][0], AIMessage)
    assert result["messages"][0].content == "final answer"


def test_build_graph_end_to_end_with_fakes():
    fake_r = FakeRetriever([_sr("ctx", "x.md")])
    fake_l = FakeLLM(response="final")

    graph = build_graph(fake_r, fake_l)
    final = graph.invoke({"messages": [HumanMessage(content="q?")]})

    assert len(final["retrieved_docs"]) == 1
    assert final["retrieved_docs"][0].chunk.source == "x.md"
    last = final["messages"][-1]
    assert isinstance(last, AIMessage)
    assert last.content == "final"
    # retriever가 마지막 user message로 검색되었는지
    assert fake_r.last_query == "q?"
    # llm prompt에 context 포함
    assert "ctx" in fake_l.last_prompt
