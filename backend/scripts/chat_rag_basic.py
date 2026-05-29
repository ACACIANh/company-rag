"""rag_basic 그래프 인터랙티브 CLI.

사용법:
    python -m scripts.chat_rag_basic

빈 줄 입력 또는 Ctrl-C 로 종료.
"""

import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import asyncpg
from pgvector.asyncpg import register_vector

from core.config import load_config
from core.embedder import SentenceTransformerEmbedder
from core.llm.factory import create_llm
from core.retriever import BasicRetriever
from core.vector_store.factory import create_vector_store

from app.graph.builder import answer_question, build_graph


def main() -> None:
    config = load_config()
    embedder = SentenceTransformerEmbedder(config.embedding_model)

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
        print("rag_basic 준비 완료. 질문을 입력하세요 (빈 줄 = 종료).")

        while True:
            try:
                question = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not question:
                break

            answer = loop.run_until_complete(answer_question(graph, question))
            print(f"\n{answer.text}\n")
            print(f"sources: {answer.sources}\n")
    finally:
        loop.run_until_complete(pool.close())
        loop.close()


if __name__ == "__main__":
    main()
