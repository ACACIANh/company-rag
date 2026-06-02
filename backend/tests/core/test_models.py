from core.models import Answer, Chunk, Document, SearchResult, SourceRef


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
    answer = Answer(text="답변", sources=[SourceRef(source="doc.md")])
    assert answer.text == "답변"
    assert answer.sources[0].source == "doc.md"
    assert answer.trace is None


def test_answer_with_trace():
    trace = [{"step": "retrieve", "count": 5}]
    answer = Answer(text="답변", sources=[SourceRef(source="doc.md")], trace=trace)
    assert answer.trace == trace


def test_document_dataclass():
    d = Document(text="hello", source="a.md")
    assert d.text == "hello"
    assert d.source == "a.md"
    assert d.metadata == {}


def test_document_with_metadata():
    d = Document(text="t", source="s", metadata={"page": 1})
    assert d.metadata == {"page": 1}


def test_chunk_has_metadata_default_empty():
    c = Chunk(text="t", source="s", chunk_id="id1")
    assert c.metadata == {}


def test_chunk_with_metadata():
    c = Chunk(text="t", source="s", chunk_id="id1", metadata={"k": "v"})
    assert c.metadata == {"k": "v"}


def test_source_ref_holds_source_path():
    from core.models import SourceRef
    ref = SourceRef(source="engineering/ops/deploy.md")
    assert ref.source == "engineering/ops/deploy.md"


def test_answer_sources_are_source_refs():
    from core.models import Answer, SourceRef
    refs = [SourceRef(source="a.md"), SourceRef(source="b.md")]
    answer = Answer(text="답변", sources=refs)
    assert len(answer.sources) == 2
    assert answer.sources[0].source == "a.md"
