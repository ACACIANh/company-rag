from unittest.mock import ANY, AsyncMock, MagicMock

from shared.indexer.indexer import Indexer
from shared.models import Chunk, Document


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
    store.add.assert_called_once_with(ANY, ANY, extra_metadata=ANY)
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


async def test_indexer_passes_extra_metadata_with_sensitivity():
    loader = MagicMock()
    loader.load.return_value = [Document(text="기밀 연봉 정보", source="secret.md")]
    chunker = MagicMock()
    chunker.chunk.return_value = [Chunk(text="기밀 연봉 정보", source="secret.md", chunk_id="c1")]
    embedder = MagicMock()
    embedder.embed_batch.return_value = [[0.1]]
    store = AsyncMock()

    indexer = Indexer(loader=loader, chunker=chunker, embedder=embedder, store=store)
    await indexer.index("/secret")

    call_kwargs = store.add.call_args[1]
    extra = call_kwargs["extra_metadata"]
    assert len(extra) == 1
    assert "sensitivity" in extra[0]


async def test_indexer_calls_fga_write_tuples_when_fga_client_provided():
    loader = MagicMock()
    loader.load.return_value = [Document(text="공개 문서", source="pub.md")]
    chunker = MagicMock()
    chunker.chunk.return_value = [Chunk(text="공개 문서", source="pub.md", chunk_id="c1")]
    embedder = MagicMock()
    embedder.embed_batch.return_value = [[0.1]]
    store = AsyncMock()
    fga_client = AsyncMock()

    indexer = Indexer(
        loader=loader, chunker=chunker, embedder=embedder, store=store, fga_client=fga_client
    )
    await indexer.index("/pub")

    fga_client.write_tuples.assert_called_once()


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
