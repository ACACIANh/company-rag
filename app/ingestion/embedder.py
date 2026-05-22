from shared.embedder import SentenceTransformerEmbedder
from shared.embedder.base import Embedder


def get_embedder(model: str) -> Embedder:
    return SentenceTransformerEmbedder(model)
