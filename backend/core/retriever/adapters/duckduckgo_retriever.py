import asyncio

from duckduckgo_search import DDGS

from core.models import Chunk, SearchResult
from core.retriever.base import Retriever


class DuckDuckGoRetriever(Retriever):
    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        where_clause: str = "",
        params: list | None = None,
    ) -> list[SearchResult]:
        def _search() -> list[dict]:
            with DDGS() as ddgs:
                return ddgs.text(query, max_results=top_k)

        raw = await asyncio.to_thread(_search)

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
