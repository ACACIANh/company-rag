from core.embedder import OpenAIEmbedder, SentenceTransformerEmbedder
from core.embedder.base import Embedder

_OPENAI_MODEL_PREFIXES = ("text-embedding-",)


def get_embedder(model: str) -> Embedder:
    if any(model.startswith(p) for p in _OPENAI_MODEL_PREFIXES):
        return OpenAIEmbedder(model)
    return SentenceTransformerEmbedder(model)
