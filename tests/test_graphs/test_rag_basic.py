from langchain_core.messages import HumanMessage

from shared.llm.base import LLMClient
from shared.models import Chunk, SearchResult
from shared.retriever.base import Retriever

from graphs.rag_basic import retrieve_node


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
