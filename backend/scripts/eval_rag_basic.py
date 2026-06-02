"""rag_basic 그래프 baseline 점수 측정.

사용법:
    python -m scripts.eval_rag_basic

선행 조건:
    python -m scripts.build_index  # 벡터 저장소가 비어있다면
"""

import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import asyncpg
from pgvector.asyncpg import register_vector

from core.config import load_config
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

        graph = build_graph(retriever, llm)
        run_eval(lambda q: loop.run_until_complete(answer_question(graph, q)))
    finally:
        loop.run_until_complete(pool.close())
        loop.close()


if __name__ == "__main__":
    main()
