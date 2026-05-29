from core.chunker import FixedSizeChunker
from core.chunker.base import Chunker
from core.models import Document


def test_chunker_implements_abc():
    assert issubclass(FixedSizeChunker, Chunker)


def test_chunk_short_doc_single_chunk():
    chunker = FixedSizeChunker(chunk_size=100, chunk_overlap=10)
    doc = Document(text="hello world", source="a.md")
    chunks = chunker.chunk(doc)
    assert len(chunks) == 1
    assert chunks[0].text == "hello world"
    assert chunks[0].source == "a.md"
    assert chunks[0].chunk_id  # non-empty uuid


def test_chunk_long_doc_multiple_chunks_no_overlap():
    text = "x" * 250
    chunker = FixedSizeChunker(chunk_size=100, chunk_overlap=0)
    chunks = chunker.chunk(Document(text=text, source="a.md"))
    assert len(chunks) == 3
    assert all(c.source == "a.md" for c in chunks)
    assert chunks[0].text == "x" * 100
    assert chunks[1].text == "x" * 100
    assert chunks[2].text == "x" * 50


def test_chunk_long_doc_with_overlap():
    text = "x" * 250
    chunker = FixedSizeChunker(chunk_size=100, chunk_overlap=20)
    chunks = chunker.chunk(Document(text=text, source="a.md"))
    # stride = 80, so starts at 0, 80, 160, 240
    assert len(chunks) == 4


def test_chunk_empty_doc():
    chunker = FixedSizeChunker(chunk_size=100, chunk_overlap=0)
    assert chunker.chunk(Document(text="", source="a.md")) == []


def test_chunk_strips_whitespace():
    chunker = FixedSizeChunker(chunk_size=100, chunk_overlap=0)
    chunks = chunker.chunk(Document(text="   hi   ", source="a.md"))
    assert len(chunks) == 1
    assert chunks[0].text == "hi"
