import pytest
import tempfile
from unittest.mock import MagicMock, patch
from shared.models import Chunk
from shared.vector_store.base import VectorStore
from shared.vector_store.chroma_store import ChromaStore
from shared.vector_store.factory import create_vector_store
from shared.config import Config


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


@pytest.fixture
def mock_qdrant_client():
    with patch("shared.vector_store.qdrant_store.QdrantClient") as mock_cls:
        mock_instance = MagicMock()
        # 기본적으로 collection이 없는 상태
        mock_instance.get_collections.return_value.collections = []
        mock_cls.return_value = mock_instance
        yield mock_instance


def test_qdrant_store_count_when_empty(mock_qdrant_client):
    from shared.vector_store.qdrant_store import QdrantStore

    store = QdrantStore(url="https://test.qdrant.io", api_key="key", collection="docs")
    assert store.count() == 0


def test_qdrant_store_add_creates_collection_and_upserts(mock_qdrant_client):
    from shared.vector_store.qdrant_store import QdrantStore

    store = QdrantStore(url="https://test.qdrant.io", api_key="key", collection="docs")
    chunks = [Chunk(text="안녕하세요", source="doc.md", chunk_id="c1")]
    embeddings = [[0.1, 0.2, 0.3]]

    store.add(chunks, embeddings)

    mock_qdrant_client.create_collection.assert_called_once()
    call_kwargs = mock_qdrant_client.create_collection.call_args.kwargs
    assert call_kwargs["collection_name"] == "docs"

    mock_qdrant_client.upsert.assert_called_once()
    upsert_kwargs = mock_qdrant_client.upsert.call_args.kwargs
    assert upsert_kwargs["collection_name"] == "docs"
    assert len(upsert_kwargs["points"]) == 1


def test_qdrant_store_add_skips_create_if_collection_exists(mock_qdrant_client):
    from shared.vector_store.qdrant_store import QdrantStore

    existing = MagicMock()
    existing.name = "docs"
    mock_qdrant_client.get_collections.return_value.collections = [existing]

    store = QdrantStore(url="https://test.qdrant.io", api_key="key", collection="docs")
    chunks = [Chunk(text="테스트", source="a.md", chunk_id="c2")]
    store.add(chunks, [[0.1, 0.2, 0.3]])

    mock_qdrant_client.create_collection.assert_not_called()


def test_qdrant_store_search_returns_results(mock_qdrant_client):
    from shared.vector_store.qdrant_store import QdrantStore

    existing = MagicMock()
    existing.name = "docs"
    mock_qdrant_client.get_collections.return_value.collections = [existing]

    hit = MagicMock()
    hit.score = 0.95
    hit.payload = {"text": "연차는 15일입니다", "source": "vacation.md", "chunk_id": "c1"}
    mock_qdrant_client.query_points.return_value.points = [hit]

    store = QdrantStore(url="https://test.qdrant.io", api_key="key", collection="docs")
    results = store.search(query_embedding=[1.0, 0.0, 0.0], top_k=1)

    assert len(results) == 1
    assert results[0].chunk.text == "연차는 15일입니다"
    assert results[0].chunk.source == "vacation.md"
    assert results[0].chunk.chunk_id == "c1"
    assert results[0].score == 0.95

    mock_qdrant_client.query_points.assert_called_once_with(
        collection_name="docs",
        query=[1.0, 0.0, 0.0],
        limit=1,
    )


def test_qdrant_store_count_after_add(mock_qdrant_client):
    from shared.vector_store.qdrant_store import QdrantStore

    existing = MagicMock()
    existing.name = "docs"
    mock_qdrant_client.get_collections.return_value.collections = [existing]
    mock_qdrant_client.count.return_value.count = 3

    store = QdrantStore(url="https://test.qdrant.io", api_key="key", collection="docs")
    assert store.count() == 3

    mock_qdrant_client.count.assert_called_once_with(collection_name="docs")


def test_qdrant_store_add_empty_does_nothing(mock_qdrant_client):
    from shared.vector_store.qdrant_store import QdrantStore

    store = QdrantStore(url="https://test.qdrant.io", api_key="key", collection="docs")
    store.add([], [])  # should not raise

    mock_qdrant_client.create_collection.assert_not_called()
    mock_qdrant_client.upsert.assert_not_called()


def test_qdrant_store_search_empty_collection_returns_empty(mock_qdrant_client):
    from shared.vector_store.qdrant_store import QdrantStore

    # collection이 없는 상태 (fixture 기본값: collections=[])
    store = QdrantStore(url="https://test.qdrant.io", api_key="key", collection="docs")
    results = store.search(query_embedding=[1.0, 0.0, 0.0], top_k=5)

    assert results == []
    mock_qdrant_client.query_points.assert_not_called()


def test_factory_creates_qdrant_store(mock_qdrant_client):
    from shared.vector_store.qdrant_store import QdrantStore

    config = Config(
        llm_provider="openai",
        llm_model="gpt-4o-mini",
        openai_api_key="",
        anthropic_api_key="",
        vector_store="qdrant",
        chroma_mode="embedded",
        chroma_path="./.chroma",
        embedding_model="paraphrase-multilingual-MiniLM-L12-v2",
        qdrant_url="https://test.qdrant.io",
        qdrant_api_key="test-key",
        qdrant_collection="my-col",
        jwt_secret="test-secret",
        jwt_expire_minutes=60,
        rate_limit_per_minute=20,
    )

    store = create_vector_store(config)

    assert isinstance(store, QdrantStore)


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
        qdrant_url="",
        qdrant_api_key="",
        qdrant_collection="documents",
        jwt_secret="test-secret",
        jwt_expire_minutes=60,
        rate_limit_per_minute=20,
    )

    store = create_vector_store(config)

    assert isinstance(store, ChromaStore)
