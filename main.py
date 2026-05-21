import argparse
import os

_ROOT = os.path.dirname(os.path.abspath(__file__))

# Task 14 will repopulate this with the new pipeline workflow path.
_WORKFLOW_PATHS = {}


def _build_index() -> None:
    from shared.config import load_config
    from shared.indexer.indexer import Indexer
    from shared.retriever.embedding import EmbeddingService
    from shared.vector_store.factory import create_vector_store

    config = load_config()
    embedder = EmbeddingService(config.embedding_model)
    store = create_vector_store(config)
    indexer = Indexer(store, embedder)
    docs_path = os.path.join(_ROOT, "docs")
    count = indexer.index_directory(docs_path)
    print(f"인덱싱 완료: {count}개 청크 ({docs_path})")


def _run_all(question: str) -> None:
    from evals.runner import print_comparison, run_all

    results = run_all(question)
    print_comparison(question, results)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="RAG Workflows 비교 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
예시:
  python main.py --build-index
  python main.py --mode pipeline -q "연차는 며칠이야?"
""",
    )
    parser.add_argument(
        "--mode",
        help="실행할 워크플로우 (Task 14 이후 'pipeline')",
    )
    parser.add_argument("--question", "-q", default=None, help="질문 문자열")
    parser.add_argument("--build-index", action="store_true", help="문서 인덱스 빌드")
    args = parser.parse_args()

    if args.build_index:
        _build_index()
        return

    if not args.mode:
        parser.print_help()
        return

    question = args.question or input("질문: ").strip()
    if not question:
        print("질문을 입력해주세요.")
        return

    _run_all(question)


if __name__ == "__main__":
    main()
