import pytest

from shared.embedder.base import Embedder


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


def test_sentence_transformer_embedder_shape():
    pytest.importorskip("sentence_transformers")
    from shared.embedder import SentenceTransformerEmbedder

    e = SentenceTransformerEmbedder("paraphrase-multilingual-MiniLM-L12-v2")
    v = e.embed("hello world")
    assert isinstance(v, list)
    assert len(v) > 0
    batch = e.embed_batch(["hello", "world"])
    assert len(batch) == 2
    assert len(batch[0]) == len(v)
