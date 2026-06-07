import asyncio
from abc import ABC, abstractmethod
from core.models import SearchResult


class Retriever(ABC):
    @abstractmethod
    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        where_clause: str = "",
        params: list | None = None,
    ) -> list[SearchResult]: ...

    async def retrieve_batch(
        self,
        queries: list[str],
        top_k: int = 5,
        where_clause: str = "",
        params: list | None = None,
    ) -> list[list[SearchResult]]:
        """여러 쿼리를 한 번에 검색해 쿼리별 결과 리스트를 반환한다.

        기본 구현은 쿼리별 retrieve를 병렬 실행한다(임베딩을 묶지 않는 웹 검색 어댑터 등에 안전).
        임베딩 비용이 큰 구현체는 이를 override해 embed_batch로 묶을 수 있다.
        """
        return list(await asyncio.gather(*(
            self.retrieve(q, top_k=top_k, where_clause=where_clause, params=params)
            for q in queries
        )))
