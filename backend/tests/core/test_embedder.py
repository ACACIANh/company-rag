import pytest

from core.embedder.base import Embedder


class _StubEmbedder(Embedder):
    def embed(self, text: str) -> list[float]:
        return [float(len(text))]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


def test_embedder_is_abc():
    with pytest.raises(TypeError):
        Embedder()  # cannot instantiate ABC


def test_stub_embedder_works():
    e = _StubEmbedder()
    assert e.embed("hi") == [2.0]
    assert e.embed_batch(["a", "bb"]) == [[1.0], [2.0]]


def test_openai_embedder_passes_timeout_and_retries(mocker):
    mock_openai = mocker.patch("core.embedder.openai_embedder.OpenAI")
    from core.embedder.openai_embedder import OpenAIEmbedder

    OpenAIEmbedder(model_name="text-embedding-3-small", api_key="test-key",
                   timeout=12.5, max_retries=4)

    assert mock_openai.call_args.kwargs["timeout"] == 12.5
    assert mock_openai.call_args.kwargs["max_retries"] == 4


def test_sentence_transformer_embedder_shape():
    pytest.importorskip("sentence_transformers")
    from core.embedder import SentenceTransformerEmbedder

    e = SentenceTransformerEmbedder("paraphrase-multilingual-MiniLM-L12-v2")
    v = e.embed("hello world")
    assert isinstance(v, list)
    assert len(v) > 0
    batch = e.embed_batch(["hello", "world"])
    assert len(batch) == 2
    assert len(batch[0]) == len(v)
