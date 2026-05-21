import argparse
import importlib.util
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))

_WORKFLOW_PATHS = {
    "simple": "workflows/01_simple/qa.py",
    "langchain": "workflows/02_1_langchain_basic/qa.py",
    "agentic": "workflows/02_2_langchain_agentic/qa.py",
    "langgraph": "workflows/03_langgraph/qa.py",
}


def _load_workflow(mode: str):
    qa_path = os.path.join(_ROOT, _WORKFLOW_PATHS[mode])
    workflow_dir = os.path.dirname(qa_path)
    sys.path.insert(0, workflow_dir)
    spec = importlib.util.spec_from_file_location(f"qa_{mode}", qa_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.path.pop(0)
    return module


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


def _run_single(mode: str, question: str) -> None:
    module = _load_workflow(mode)
    answer = module.run(question)
    print(f"\n답변: {answer.text}")
    print(f"출처: {', '.join(answer.sources) or '없음'}")
    if answer.trace:
        print(f"\n[trace — {len(answer.trace)}단계]")
        for step in answer.trace:
            print(f"  {step}")


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
  python main.py --mode simple -q "연차는 며칠이야?"
  python main.py --mode all -q "코드 리뷰 가이드가 뭐야?"
""",
    )
    parser.add_argument(
        "--mode",
        choices=["simple", "langchain", "agentic", "langgraph", "all"],
        help="실행할 워크플로우",
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

    if args.mode == "all":
        _run_all(question)
    else:
        _run_single(args.mode, question)


if __name__ == "__main__":
    main()
