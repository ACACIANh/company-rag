"""rag_basic 그래프 baseline 점수 측정.

사용법:
    python -m scripts.eval_rag_basic

선행 조건:
    python -m scripts.build_index  # 벡터 저장소가 비어있다면
"""

import asyncio
import os
import sys
from types import SimpleNamespace

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import asyncpg
from pgvector.asyncpg import register_vector

from core.config import load_config
from core.fga.cache import make_cache_backend
from core.fga.client import FGAClient
from core.fga.models import FGAConfig
from core.llm.factory import create_llm
from core.retriever import BasicRetriever
from core.vector_store.factory import create_vector_store

from app.graph.builder import answer_question, build_graph
from app.ingestion.embedder import get_embedder
from tests.eval.runner import run_eval


def main() -> None:
    config = load_config()
    embedder = get_embedder(config.embedding_model)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def _init_conn(conn):
        await register_vector(conn)

    pool = loop.run_until_complete(
        asyncpg.create_pool(config.postgres_dsn, init=_init_conn)
    )
    try:
        store = create_vector_store(config, pool)
        retriever = BasicRetriever(store=store, embedder=embedder)
        llm = create_llm(config)

        cache_backend = make_cache_backend(config.fga_cache_backend, pool)
        if hasattr(cache_backend, "ensure_table"):
            loop.run_until_complete(cache_backend.ensure_table())
        fga_config = FGAConfig(
            api_url=config.fga_api_url,
            store_id=config.fga_store_id,
            api_key=config.fga_api_key,
            cache_ttl_seconds=config.fga_cache_ttl_seconds,
        )
        fga_client = FGAClient(config=fga_config, cache=cache_backend, pg_pool=pool)

        graph = build_graph(retriever, llm, fga_client=fga_client)

        def _run(question: str):
            # 전사 열람권(c_level super_reader) 사용자로 평가 — 권한 필터가 검색 품질 측정을 가리지 않도록.
            ans = loop.run_until_complete(
                answer_question(graph, question, user_id="user-admin")
            )
            # 인용 source(폴더상대 'common/x.md') → basename 으로 변환.
            # questions.yaml 의 expected_source 는 basename 이고, 지표(recall/mrr)는
            # list[str] 를 기대하므로 SourceRef → 파일명 문자열로 맞춘다.
            return SimpleNamespace(
                text=ans.text,
                sources=[os.path.basename(s.source) for s in ans.sources],
            )

        run_eval(_run)
    finally:
        loop.run_until_complete(pool.close())
        loop.close()


if __name__ == "__main__":
    main()
