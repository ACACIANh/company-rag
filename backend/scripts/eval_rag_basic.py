"""rag_basic 그래프 baseline 점수 측정.

사용법:
    python -m scripts.eval_rag_basic

선행 조건:
    python -m scripts.build_index  # 벡터 저장소가 비어있다면
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from shared.config import load_config
from shared.embedder import SentenceTransformerEmbedder
from shared.llm.factory import create_llm
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

    graph = build_graph(retriever, llm)
    run_eval(lambda q: answer_question(graph, q))


if __name__ == "__main__":
    main()
