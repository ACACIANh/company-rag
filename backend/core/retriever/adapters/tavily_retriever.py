import asyncio

from tavily import TavilyClient

from core.models import Chunk, SearchResult
from core.retriever.base import Retriever


class TavilyRetriever(Retriever):
    def __init__(self, api_key: str) -> None:
        self._client = TavilyClient(api_key=api_key)

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        where_clause: str = "",
        params: list | None = None,
    ) -> list[SearchResult]:
        response = await asyncio.to_thread(
            self._client.search, query, max_results=top_k
        )
        return [
            SearchResult(
                chunk=Chunk(
                    text=r["content"],
                    source=r["url"],
                    chunk_id=r["url"],
                ),
                score=r.get("score", 0.5),
            )
            for r in response.get("results", [])
        ]
