import pytest
import tempfile
import inspect
from shared.models import Chunk
from shared.vector_store.base import VectorStore
from shared.vector_store.chroma_store import ChromaStore
from shared.vector_store.factory import create_vector_store
from shared.config import Config


def test_vector_store_add_is_coroutinefunction():
    assert inspect.iscoroutinefunction(VectorStore.add)


def test_vector_store_search_is_coroutinefunction():
    assert inspect.iscoroutinefunction(VectorStore.search)


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


def test_chroma_store_search_populates_metadata(chroma_store):
    chunks = [Chunk(text="내용", source="doc.md", chunk_id="c1")]
    extra = [{"sensitivity": "internal", "team_id": "team:dev", "document_id": "doc:1"}]
    chroma_store.add(chunks, [[0.1, 0.2, 0.3]], extra_metadata=extra)

    results = chroma_store.search(query_embedding=[0.1, 0.2, 0.3], top_k=1)

    assert results[0].chunk.metadata.get("sensitivity") == "internal"
    assert results[0].chunk.metadata.get("team_id") == "team:dev"
    assert results[0].chunk.metadata.get("document_id") == "doc:1"
    assert results[0].chunk.metadata.get("source") == "doc.md"


def test_factory_creates_chroma_store_by_default(tmp_path):
    from shared.vector_store.chroma_store import ChromaStore

    config = Config(
        llm_provider="openai",
        llm_model="gpt-4o-mini",
        openai_api_key="",
        anthropic_api_key="",
        vector_store="chroma",
        chroma_mode="embedded",
        chroma_path=str(tmp_path),
        embedding_model="paraphrase-multilingual-MiniLM-L12-v2",
        jwt_secret="test-secret",
        jwt_expire_minutes=60,
        rate_limit_per_minute=20,
        cors_origins=["http://localhost:5173"],
        reranker_type="none",
        reranker_base_url="",
        reranker_model="",
        reranker_api_key="",
        session_store_type="memory",
        postgres_dsn="",
        fga_api_url="http://localhost:8080",
        fga_store_id="",
        fga_api_key="",
        fga_cache_backend="memory",
        fga_cache_ttl_seconds=60,
    )

    store = create_vector_store(config)

    assert isinstance(store, ChromaStore)
