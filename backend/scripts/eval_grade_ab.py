"""grade 휴리스틱 전환의 eval 회귀 게이트 — 전체 그래프 종단 keyword_hit_rate 측정.

doc_search 질문을 전사 열람권 유저(user-admin=c_level)로 종단 실행해 답변의
keyword_hit_rate와 recall@5를 집계한다. A/B는 같은 스크립트를 두 번 돌려 비교:
  1) 현재 브랜치(휴리스틱 grade)
  2) git checkout main -- app/graph/nodes/grade_documents.py app/graph/builder.py (LLM grade)
     로 grade만 baseline으로 되돌린 뒤 재실행 → 끝나면 브랜치 버전 복원

사용: cd backend && LANGCHAIN_TRACING_V2=false .venv/bin/python -m scripts.eval_grade_ab --label heuristic
"""
import argparse
import asyncio
import uuid

import asyncpg
from pgvector.asyncpg import register_vector

from core.config import load_config
from core.fga.cache.memory import InMemoryCacheBackend
from core.fga.client import FGAClient
from core.fga.models import FGAConfig
from core.llm.factory import create_llm
from core.observability.eval.metrics import keyword_hit_rate, recall_at_k
from core.vector_store.factory import create_vector_store
from core.retriever import BasicRetriever
from app.graph.builder import answer_question, build_graph
from app.ingestion.embedder import get_embedder
from tests.eval.runner import load_questions

_USER = "user-admin"  # c_level → super_reader(전사 열람) → FGA pre-filter 통과
_NO_DOC = "관련 사내 문서를 찾지 못했습니다"


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="")
    args = ap.parse_args()

    config = load_config()
    embedder = get_embedder(config.embedding_model)

    async def _init_conn(conn):
        await register_vector(conn)

    pool = await asyncpg.create_pool(config.postgres_dsn, init=_init_conn, min_size=1, max_size=4)
    fga = None
    try:
        store = create_vector_store(config, pool)
        retriever = BasicRetriever(store=store, embedder=embedder)
        llm = create_llm(config)
        fga = FGAClient(
            config=FGAConfig(
                api_url=config.fga_api_url, store_id=config.fga_store_id,
                api_key=config.fga_api_key, cache_ttl_seconds=config.fga_cache_ttl_seconds,
            ),
            cache=InMemoryCacheBackend(), pg_pool=pool,
        )
        graph = build_graph(
            retriever=retriever, llm=llm, reranker=None, fga_client=fga,
            retrieve_top_k=20, top_k=5,
        )

        questions = [q for q in load_questions() if q.get("expected_source")]
        print(f"=== EVAL [{args.label}]  {len(questions)} doc_search 질문, user={_USER} ===")

        kw_scores, recalls, n_nodoc = [], [], 0
        for q in questions:
            config_q = {"configurable": {"thread_id": f"evalab-{uuid.uuid4()}"}}
            ans = await answer_question(graph, q["question"], config=config_q, user_id=_USER)
            sources = [s.source for s in ans.sources]
            kw = keyword_hit_rate(ans.text, q.get("expected_keywords", []))
            rc = recall_at_k(sources, q["expected_source"], 5)
            kw_scores.append(kw)
            recalls.append(rc)
            nodoc = _NO_DOC in ans.text
            if nodoc:
                n_nodoc += 1
            print(f"  kw={kw:.2f} recall@5={rc:.0f} {'[NO_DOC]' if nodoc else '        '} {q['question'][:32]}")

        n = len(questions)
        print(f"\n--- [{args.label}] 집계 ---")
        print(f"  mean keyword_hit_rate = {sum(kw_scores)/n:.4f}")
        print(f"  mean recall@5         = {sum(recalls)/n:.4f}")
        print(f"  NO_DOC(거부) 건수      = {n_nodoc}/{n}")
    finally:
        if fga is not None:
            await fga.aclose()
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
