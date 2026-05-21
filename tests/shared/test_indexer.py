from unittest.mock import MagicMock

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
    store.add.assert_called_once()
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
