from core.embedder.base import Embedder


class LangChainEmbeddingsAdapter:
    """LangChain Embeddings interface(embed_documents/embed_query) adapter for our Embedder."""

    def __init__(self, embedder: Embedder) -> None:
        self._embedder = embedder

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embedder.embed_batch(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._embedder.embed(text)
