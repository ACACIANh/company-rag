from duckduckgo_search import DDGS

from shared.models import Chunk, SearchResult
from shared.retriever.base import Retriever


class DuckDuckGoRetriever(Retriever):
    def retrieve(self, query: str, top_k: int = 5) -> list[SearchResult]:
        with DDGS() as ddgs:
            raw = ddgs.text(query, max_results=top_k)

        return [
            SearchResult(
                chunk=Chunk(text=r["body"], source=r["href"], chunk_id=r["href"]),
                score=0.5,
            )
            for r in raw
        ]
