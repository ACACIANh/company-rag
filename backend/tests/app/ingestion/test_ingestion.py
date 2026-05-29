def test_get_chunker_returns_chunker():
    from core.chunker.base import Chunker
    from app.ingestion.chunker import get_chunker
    assert isinstance(get_chunker(), Chunker)


def test_get_embedder_sentence_transformer():
    from core.embedder.base import Embedder
    from app.ingestion.embedder import get_embedder
    assert isinstance(get_embedder("paraphrase-multilingual-MiniLM-L12-v2"), Embedder)


def test_get_embedder_openai(mocker):
    mocker.patch("core.embedder.openai_embedder.OpenAI")
    from core.embedder.base import Embedder
    from app.ingestion.embedder import get_embedder
    assert isinstance(get_embedder("text-embedding-3-small"), Embedder)


def test_build_index_function_exists():
    from app.ingestion.indexer import build_index
    import inspect
    assert inspect.isfunction(build_index)
    sig = inspect.signature(build_index)
    assert "docs_path" in sig.parameters
