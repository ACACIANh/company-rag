"""rag_basic 그래프 인터랙티브 CLI.

사용법:
    python -m scripts.chat_rag_basic

빈 줄 입력 또는 Ctrl-C 로 종료.
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


def main() -> None:
    config = load_config()
    embedder = SentenceTransformerEmbedder(config.embedding_model)
    store = create_vector_store(config)
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

        answer = answer_question(graph, question)
        print(f"\n{answer.text}\n")
        print(f"sources: {answer.sources}\n")


if __name__ == "__main__":
    main()
