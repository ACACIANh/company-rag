import pytest
import tempfile
from shared.models import Chunk
from shared.vector_store.base import VectorStore
from shared.vector_store.chroma_store import ChromaStore


def test_vector_store_is_abstract():
    with pytest.raises(TypeError):
        VectorStore()


@pytest.fixture
def chroma_store(tmp_path):
    return ChromaStore(path=str(tmp_path), mode="embedded")


def test_chroma_store_initially_empty(chroma_store):
    assert chroma_store.count() == 0


def test_chroma_store_add_and_count(chroma_store):
    chunks = [Chunk(text="안녕하세요", source="doc.md", chunk_id="c1")]
    embeddings = [[0.1, 0.2, 0.3]]
    chroma_store.add(chunks, embeddings)
    assert chroma_store.count() == 1


def test_chroma_store_search(chroma_store):
    chunks = [
        Chunk(text="연차는 15일입니다", source="vacation.md", chunk_id="c1"),
        Chunk(text="점심시간은 1시간입니다", source="policy.md", chunk_id="c2"),
    ]
    embeddings = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    chroma_store.add(chunks, embeddings)

    results = chroma_store.search(query_embedding=[1.0, 0.0, 0.0], top_k=1)

    assert len(results) == 1
    assert results[0].chunk.source == "vacation.md"
    assert results[0].score >= 0
