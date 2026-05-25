from unittest.mock import ANY, MagicMock

from shared.indexer.indexer import Indexer
from shared.models import Chunk, Document


def test_indexer_composes_loader_chunker_embedder_store():
    loader = MagicMock()
    loader.load.return_value = [Document(text="hello world", source="a.md")]

    chunker = MagicMock()
    chunker.chunk.return_value = [
        Chunk(text="hello world", source="a.md", chunk_id="c1")
    ]

    embedder = MagicMock()
    embedder.embed_batch.return_value = [[0.1, 0.2, 0.3]]

    store = MagicMock()

    indexer = Indexer(loader=loader, chunker=chunker, embedder=embedder, store=store)
    count = indexer.index("/some/path")

    loader.load.assert_called_once_with("/some/path")
    chunker.chunk.assert_called_once()
    embedder.embed_batch.assert_called_once_with(["hello world"])
    store.add.assert_called_once_with(ANY, ANY, extra_metadata=ANY)
    assert count == 1


def test_indexer_empty_docs_skips_store_add():
    loader = MagicMock()
    loader.load.return_value = []
    chunker = MagicMock()
    embedder = MagicMock()
    store = MagicMock()

    indexer = Indexer(loader=loader, chunker=chunker, embedder=embedder, store=store)
    count = indexer.index("/empty")

    assert count == 0
    chunker.chunk.assert_not_called()
    embedder.embed_batch.assert_not_called()
    store.add.assert_not_called()


def test_indexer_concatenates_chunks_from_multiple_docs():
    loader = MagicMock()
    loader.load.return_value = [
        Document(text="A", source="a.md"),
        Document(text="B", source="b.md"),
    ]
    chunker = MagicMock()
    chunker.chunk.side_effect = [
        [Chunk(text="A", source="a.md", chunk_id="ca")],
        [Chunk(text="B", source="b.md", chunk_id="cb")],
    ]
    embedder = MagicMock()
    embedder.embed_batch.return_value = [[0.1], [0.2]]
    store = MagicMock()

    Indexer(loader=loader, chunker=chunker, embedder=embedder, store=store).index("/p")

    embedder.embed_batch.assert_called_once_with(["A", "B"])
    assert store.add.call_count == 1


def test_indexer_passes_extra_metadata_with_sensitivity():
    loader = MagicMock()
    loader.load.return_value = [Document(text="기밀 연봉 정보", source="secret.md")]

    chunker = MagicMock()
    chunker.chunk.return_value = [
        Chunk(text="기밀 연봉 정보", source="secret.md", chunk_id="c1")
    ]

    embedder = MagicMock()
    embedder.embed_batch.return_value = [[0.1]]

    store = MagicMock()

    Indexer(loader=loader, chunker=chunker, embedder=embedder, store=store).index("/p")

    _, _, kwargs = store.add.mock_calls[0]
    extra = kwargs["extra_metadata"]
    assert len(extra) == 1
    assert extra[0]["sensitivity"] == "secret"
    assert extra[0]["document_id"] == "doc:secret.md"


def test_indexer_calls_fga_write_tuples_when_fga_client_provided():
    loader = MagicMock()
    loader.load.return_value = [Document(text="공개 문서", source="pub.md")]

    chunker = MagicMock()
    chunker.chunk.return_value = [
        Chunk(text="공개 문서", source="pub.md", chunk_id="c1")
    ]

    embedder = MagicMock()
    embedder.embed_batch.return_value = [[0.1]]

    store = MagicMock()
    fga_client = MagicMock()

    Indexer(
        loader=loader,
        chunker=chunker,
        embedder=embedder,
        store=store,
        fga_client=fga_client,
    ).index("/p")

    fga_client.write_tuples.assert_called_once_with(
        doc_id="doc:pub.md",
        owner_id="user:system",
        team_id="team:general",
        sensitivity="public",
    )


def test_indexer_skips_fga_when_no_fga_client():
    loader = MagicMock()
    loader.load.return_value = [Document(text="hello", source="a.md")]

    chunker = MagicMock()
    chunker.chunk.return_value = [Chunk(text="hello", source="a.md", chunk_id="c1")]

    embedder = MagicMock()
    embedder.embed_batch.return_value = [[0.1]]

    store = MagicMock()

    # fga_client=None (default) — no AttributeError should be raised
    count = Indexer(loader=loader, chunker=chunker, embedder=embedder, store=store).index("/p")
    assert count == 1
