from shared.models import Chunk, SearchResult, Answer


def test_chunk_fields():
    chunk = Chunk(text="hello", source="doc.md", chunk_id="abc-123")
    assert chunk.text == "hello"
    assert chunk.source == "doc.md"
    assert chunk.chunk_id == "abc-123"


def test_search_result_fields():
    chunk = Chunk(text="hello", source="doc.md", chunk_id="abc-123")
    result = SearchResult(chunk=chunk, score=0.9)
    assert result.chunk is chunk
    assert result.score == 0.9


def test_answer_defaults():
    answer = Answer(text="답변", sources=["doc.md"])
    assert answer.text == "답변"
    assert answer.sources == ["doc.md"]
    assert answer.trace is None


def test_answer_with_trace():
    trace = [{"step": "retrieve", "count": 5}]
    answer = Answer(text="답변", sources=["doc.md"], trace=trace)
    assert answer.trace == trace
