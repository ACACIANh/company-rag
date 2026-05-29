"""baseline(NoOp) vs LLMReranker 비교 eval.

사용법:
    RERANKER_API_KEY=sk-... python -m tests.eval.compare_reranker

환경 변수:
    RERANKER_API_KEY  — OpenAI API 키 (없으면 OPENAI_API_KEY fallback)
    RERANKER_BASE_URL — 사내 LLM URL (없으면 OpenAI 기본값)
    RERANKER_MODEL    — 기본 gpt-4o-mini
"""
import asyncio
import os
import sys

import asyncpg
from openai import OpenAI
from pgvector.asyncpg import register_vector

from core.config import load_config
from core.embedder import SentenceTransformerEmbedder
from core.llm.factory import create_llm
from core.reranker.llm_reranker import LLMReranker
from core.vector_store.factory import create_vector_store
from core.retriever import BasicRetriever
from app.graph.builder import answer_question, build_graph
from tests.eval.runner import load_questions, run_eval

_DOC_SEARCH_YAML = os.path.join(os.path.dirname(__file__), "questions.yaml")


def _make_run(loop, graph):
    def run(question: str):
        return loop.run_until_complete(answer_question(graph, question))
    return run


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

        # expected_source 있는 질문만 필터 (recall 측정 가능 = doc_search 대상)
        questions = [q for q in load_questions(_DOC_SEARCH_YAML) if q.get("expected_source")]
        if not questions:
            print("doc_search 질문이 없습니다.")
            sys.exit(1)

        import pathlib
        import tempfile

        import yaml
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8")
        yaml.dump({"questions": questions}, tmp, allow_unicode=True)
        tmp.close()
        filtered_yaml = tmp.name

        # --- baseline: reranker 없이 top_k=5 ---
        baseline_graph = build_graph(retriever=retriever, llm=llm, reranker=None, retrieve_top_k=5, top_k=5)
        run_eval(_make_run(loop, baseline_graph), yaml_path=filtered_yaml, label="baseline (NoRerank, top_k=5)")

        # --- LLMReranker: top_k=20 → rerank → top_k=5 ---
        api_key = config.reranker_api_key or config.openai_api_key
        base_url = config.reranker_base_url or None
        if not api_key:
            print("\nRERANKER_API_KEY 또는 OPENAI_API_KEY가 없습니다. LLMReranker eval을 건너뜁니다.")
            pathlib.Path(filtered_yaml).unlink(missing_ok=True)
            return

        client = OpenAI(api_key=api_key, base_url=base_url)
        reranker = LLMReranker(client=client, model=config.reranker_model)
        reranker_graph = build_graph(retriever=retriever, llm=llm, reranker=reranker, retrieve_top_k=20, top_k=5)
        run_eval(_make_run(loop, reranker_graph), yaml_path=filtered_yaml, label="LLMReranker (top_k=20→5)")

        pathlib.Path(filtered_yaml).unlink(missing_ok=True)
    finally:
        loop.run_until_complete(pool.close())
        loop.close()


if __name__ == "__main__":
    main()
