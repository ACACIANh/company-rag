from duckduckgo_search import DDGS

from core.models import Chunk, SearchResult
from core.retriever.base import Retriever


class DuckDuckGoRetriever(Retriever):
    def retrieve(self, query: str, top_k: int = 5) -> list[SearchResult]:
        with DDGS() as ddgs:
            raw = ddgs.text(query, max_results=top_k)

        return [
            SearchResult(
                chunk=Chunk(
                    text=r.get("body", ""),
                    source=r.get("href", ""),
                    chunk_id=r.get("href", ""),
                ),
                score=0.5,
            )
            for r in raw
            if r.get("href")
        ]
