"""Reranker 전후 recall@1/3/5 + MRR 비교 스크립트.

사용법:
    python -m scripts.eval_reranker

선행 조건:
    python -m scripts.build_index  # 벡터 저장소가 비어있다면
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from openai import OpenAI

from shared.config import load_config
from shared.embedder import SentenceTransformerEmbedder
from shared.llm.factory import create_llm
from shared.reranker import LLMReranker, NoOpReranker
from shared.retriever import BasicRetriever
from shared.vector_store.factory import create_vector_store

from app.graph.builder import answer_question, build_graph
from tests.eval.runner import run_eval


def main() -> None:
    config = load_config()
    embedder = SentenceTransformerEmbedder(config.embedding_model)
    store = create_vector_store(config)
    retriever = BasicRetriever(store=store, embedder=embedder)
    llm = create_llm(config)

    # ── Baseline: retrieve top-5, 재정렬 없음 (기존 동작) ──────────────
    baseline_graph = build_graph(
        retriever, llm,
        reranker=NoOpReranker(),
        retrieve_top_k=5,
        top_k=5,
    )
    run_eval(
        lambda q: answer_question(baseline_graph, q),
        label="baseline (top-5, no rerank)",
    )

    # ── Reranker: retrieve top-20, LLM으로 재정렬 후 top-5 ─────────────
    openai_client = OpenAI(
        api_key=config.openai_api_key,
        # 사내 LLM 전환 시: base_url="https://사내LLM주소/v1"
    )
    reranker = LLMReranker(openai_client, model=config.llm_model)
    reranker_graph = build_graph(
        retriever, llm,
        reranker=reranker,
        retrieve_top_k=20,
        top_k=5,
    )
    run_eval(
        lambda q: answer_question(reranker_graph, q),
        label="reranker (top-20 → LLM → top-5)",
    )


if __name__ == "__main__":
    main()
