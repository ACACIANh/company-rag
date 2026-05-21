import argparse
import os

from shared.chunker import FixedSizeChunker
from shared.config import load_config
from shared.embedder import SentenceTransformerEmbedder
from shared.indexer.indexer import Indexer
from shared.loader import MarkdownLoader
from shared.observability.cache import CachedEmbedder, LRUCache
from shared.vector_store.factory import create_vector_store

_ROOT = os.path.dirname(os.path.abspath(__file__))


def _build_index() -> None:
    config = load_config()
    embedder = CachedEmbedder(
        SentenceTransformerEmbedder(config.embedding_model),
        LRUCache(max_size=4096),
    )
    store = create_vector_store(config)
    indexer = Indexer(
        loader=MarkdownLoader(),
        chunker=FixedSizeChunker(chunk_size=500, chunk_overlap=50),
        embedder=embedder,
        store=store,
    )
    docs_path = os.path.join(_ROOT, "docs")
    count = indexer.index(docs_path)
    print(f"인덱싱 완료: {count}개 청크 ({docs_path})")


def _run_pipeline(question: str) -> None:
    from workflows.pipeline.qa import run

    answer = run(question)
    print(f"\n답변: {answer.text}")
    print(f"출처: {', '.join(answer.sources) or '없음'}")
    if answer.trace:
        print(f"\n[trace — {len(answer.trace)}단계]")
        for step in answer.trace:
            print(f"  {step}")


def _run_all(question: str) -> None:
    from eval_suite.runner import print_comparison, run_all

    results = run_all(question)
    print_comparison(question, results)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="RAG Pipeline CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
예시:
  python main.py --build-index
  python main.py --mode pipeline -q "연차는 며칠이야?"
  python main.py --mode all -q "코드 리뷰 가이드가 뭐야?"
""",
    )
    parser.add_argument(
        "--mode",
        choices=["pipeline", "all"],
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
        _run_pipeline(question)


if __name__ == "__main__":
    main()
