"""docs/ 디렉터리를 청크로 분할하여 벡터 저장소에 인덱싱한다.

사용법:
    python -m scripts.build_index
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from app.ingestion.indexer import build_index


def main() -> None:
    docs_path = os.path.join(_ROOT, "docs")
    build_index(docs_path)


if __name__ == "__main__":
    main()
