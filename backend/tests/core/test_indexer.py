import pytest
from unittest.mock import ANY, AsyncMock, MagicMock

from core.indexer.indexer import Indexer
from core.models import Chunk, Document


async def test_indexer_composes_loader_chunker_embedder_store():
    loader = MagicMock()
    loader.load.return_value = [Document(text="hello world", source="a.md")]
    chunker = MagicMock()
    chunker.chunk.return_value = [Chunk(text="hello world", source="a.md", chunk_id="c1")]
    embedder = MagicMock()
    embedder.embed_batch.return_value = [[0.1, 0.2, 0.3]]
    store = AsyncMock()

    indexer = Indexer(loader=loader, chunker=chunker, embedder=embedder, store=store)
    count = await indexer.index("/some/path")

    loader.load.assert_called_once_with("/some/path")
    chunker.chunk.assert_called_once()
    embedder.embed_batch.assert_called_once_with(["hello world"])
    store.add.assert_called_once_with(ANY, ANY)
    assert count == 1


async def test_indexer_empty_docs_skips_store_add():
    loader = MagicMock()
    loader.load.return_value = []
    chunker = MagicMock()
    embedder = MagicMock()
    store = AsyncMock()

    indexer = Indexer(loader=loader, chunker=chunker, embedder=embedder, store=store)
    count = await indexer.index("/empty")

    assert count == 0
    chunker.chunk.assert_not_called()
    embedder.embed_batch.assert_not_called()
    store.add.assert_not_called()


async def test_indexer_concatenates_chunks_from_multiple_docs():
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
    store = AsyncMock()

    await Indexer(loader=loader, chunker=chunker, embedder=embedder, store=store).index("/p")

    embedder.embed_batch.assert_called_once_with(["A", "B"])
    assert store.add.call_count == 1


async def test_indexer_skips_fga_when_no_fga_client():
    loader = MagicMock()
    loader.load.return_value = [Document(text="내용", source="doc.md")]
    chunker = MagicMock()
    chunker.chunk.return_value = [Chunk(text="내용", source="doc.md", chunk_id="c1")]
    embedder = MagicMock()
    embedder.embed_batch.return_value = [[0.1]]
    store = AsyncMock()

    indexer = Indexer(loader=loader, chunker=chunker, embedder=embedder, store=store)
    await indexer.index("/doc")  # no fga_client → no error, no FGA call
    store.add.assert_called_once()


@pytest.mark.asyncio
async def test_index_saves_originals_when_store_given():
    from unittest.mock import AsyncMock, MagicMock

    from core.indexer.indexer import Indexer
    from core.models import Chunk, Document

    loader = MagicMock()
    loader.load = MagicMock(return_value=[
        Document(text="hello", source="eng/a.pdf", metadata={"path": "/c/eng"},
                 raw=b"raw", mime="application/pdf"),
    ])
    chunker = MagicMock()
    chunker.chunk = MagicMock(return_value=[Chunk(text="hello", source="eng/a.pdf", chunk_id="1")])
    embedder = MagicMock()
    embedder.embed_batch = MagicMock(return_value=[[0.1]])
    store = AsyncMock()
    original_store = AsyncMock()

    await Indexer(loader, chunker, embedder, store, original_store=original_store).index("p")

    original_store.save.assert_awaited_once_with(
        "/c/eng/a.pdf", "/c/eng", "a.pdf", "application/pdf", b"raw"
    )


@pytest.mark.asyncio
async def test_index_without_original_store_does_not_fail():
    from unittest.mock import AsyncMock, MagicMock

    from core.indexer.indexer import Indexer
    from core.models import Chunk, Document

    loader = MagicMock()
    loader.load = MagicMock(return_value=[Document(text="x", source="a.md", metadata={"path": "/c"})])
    chunker = MagicMock()
    chunker.chunk = MagicMock(return_value=[Chunk(text="x", source="a.md", chunk_id="1")])
    embedder = MagicMock()
    embedder.embed_batch = MagicMock(return_value=[[0.1]])
    store = AsyncMock()

    n = await Indexer(loader, chunker, embedder, store).index("p")
    assert n == 1
