"""grade_documents 휴리스틱 임계 보정 — LLM grade를 top-cosine 임계로 대체하기 위한 측정.

eval 질문(생성해야 정상) vs off-topic 질문(거부해야 정상)에 대해
(a) 검색 top-cosine = max(d.score)  (b) 현행 LLM grade 점수 를 함께 수집해,
어떤 COSINE_THRESHOLD가 두 집단을 분리하면서 eval을 오거부하지 않는지 찾는다.

프로덕션 grade는 rerank된 top_k=5 documents를 보므로 여기서도 docs[:5]만 채점한다
(RERANKER_TYPE 미설정=NoOp → cosine 내림차순 → docs[0].score == max).

사용: cd backend && LANGCHAIN_TRACING_V2=false .venv/bin/python -m scripts.calibrate_grade
"""
import asyncio
import re
import statistics

import asyncpg
from pgvector.asyncpg import register_vector

from core.config import load_config
from core.llm.factory import create_llm
from core.vector_store.factory import create_vector_store
from core.retriever import BasicRetriever
from app.ingestion.embedder import get_embedder
from app.graph.prompts import GRADE_DOCUMENTS
from tests.eval.runner import load_questions

# 코퍼스 밖/무관 질문 — grade가 거부(생성 안 함)해야 정상
_OFF_TOPIC = [
    "오늘 서울 날씨 어때?",
    "파이썬으로 퀵소트 구현해줘",
    "김치찌개 레시피 알려줘",
    "2026 월드컵 우승 후보는?",
    "비트코인 지금 얼마야?",
]
_RETRIEVE_TOP_K = 20
_GRADE_TOP_K = 5  # 프로덕션 retrieve_node top_k


def _llm_grade(llm, question: str, docs: list) -> float:
    """폐기된 LLM grade 로직을 보정 비교용으로 자립 재현(grade_documents.py 휴리스틱 전환 전 버전)."""
    if not docs:
        return 0.0
    context = "\n\n".join(d.chunk.text for d in docs)
    prompt = GRADE_DOCUMENTS.format(question=question, context=context)
    response = llm.complete(prompt).strip()
    match = re.search(r"([01](?:\.\d+)?)", response)
    score = float(match.group(1)) if match else 0.0
    return min(max(score, 0.0), 1.0)


async def _measure(retriever, llm, question: str):
    docs = await retriever.retrieve(question, top_k=_RETRIEVE_TOP_K, where_clause="")
    top = docs[:_GRADE_TOP_K]
    top_cosine = max((d.score for d in top), default=0.0)
    llm_score = _llm_grade(llm, question, top)
    return top_cosine, llm_score, [d.chunk.source for d in top]


async def main() -> None:
    config = load_config()
    embedder = get_embedder(config.embedding_model)

    async def _init_conn(conn):
        await register_vector(conn)

    pool = await asyncpg.create_pool(config.postgres_dsn, init=_init_conn, min_size=1, max_size=4)
    try:
        store = create_vector_store(config, pool)
        retriever = BasicRetriever(store=store, embedder=embedder)
        llm = create_llm(config)

        n_docs = await store.count()
        print(f"corpus documents: {n_docs}")

        eval_qs = [q for q in load_questions() if q.get("expected_source")]

        print(f"\n=== eval 질문 {len(eval_qs)}개 (생성해야 정상) ===")
        eval_cos, eval_llm, eval_false_rej = [], [], 0
        for q in eval_qs:
            cos, score, top5 = await _measure(retriever, llm, q["question"])
            hit = q["expected_source"] in top5
            eval_cos.append(cos)
            eval_llm.append(score)
            if score < 0.5:
                eval_false_rej += 1
            print(f"  cos={cos:.3f} llm={score:.2f} src@5={'Y' if hit else 'N'}  {q['question'][:34]}")

        print(f"\n=== off-topic {len(_OFF_TOPIC)}개 (거부해야 정상) ===")
        rej_cos, rej_llm = [], []
        for question in _OFF_TOPIC:
            cos, score, _ = await _measure(retriever, llm, question)
            rej_cos.append(cos)
            rej_llm.append(score)
            print(f"  cos={cos:.3f} llm={score:.2f}  {question[:34]}")

        print("\n=== 요약 ===")
        print(f"eval top_cosine: min={min(eval_cos):.3f} median={statistics.median(eval_cos):.3f} max={max(eval_cos):.3f}")
        print(f"  LLM이 거부(<0.5)한 eval 질문: {eval_false_rej}/{len(eval_qs)}")
        print(f"off-topic top_cosine: min={min(rej_cos):.3f} median={statistics.median(rej_cos):.3f} max={max(rej_cos):.3f}")
        print(f"  LLM이 거부한 off-topic: {sum(1 for s in rej_llm if s < 0.5)}/{len(_OFF_TOPIC)}")

        gap_lo, gap_hi = max(rej_cos), min(eval_cos)
        print(f"\n분리 구간: off-topic max={gap_lo:.3f}  <T<  eval min={gap_hi:.3f}  (gap {'존재' if gap_hi > gap_lo else '없음!'})")
        for t in [0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]:
            fr = sum(1 for c in eval_cos if c < t)   # eval 오거부(나쁨)
            cr = sum(1 for c in rej_cos if c < t)    # off-topic 정상거부(좋음)
            print(f"  T={t:.2f}: eval 오거부 {fr}/{len(eval_cos)}, off-topic 거부 {cr}/{len(rej_cos)}")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
