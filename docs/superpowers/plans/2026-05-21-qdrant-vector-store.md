# Qdrant Vector Store 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `shared/vector_store`에 Qdrant Cloud를 지원하는 `QdrantStore`를 추가하고, `VECTOR_STORE=qdrant` 환경변수로 선택 가능하게 한다.

**Architecture:** 기존 `VectorStore` ABC를 구현하는 `QdrantStore` 클래스를 추가한다. Collection은 첫 `add()` 호출 시 벡터 차원을 알 수 있으므로 lazy 생성한다. `Config`에 Qdrant 전용 필드 3개를 추가하고 `factory.py`에 분기를 추가한다.

**Tech Stack:** `qdrant-client>=1.7.0`, `pytest`, `unittest.mock`

---

## 파일 변경 목록

| 파일 | 작업 |
|------|------|
| `requirements.txt` | `qdrant-client>=1.7.0` 추가 |
| `shared/config.py` | `qdrant_url`, `qdrant_api_key`, `qdrant_collection` 필드 추가 |
| `shared/vector_store/qdrant_store.py` | 신규 생성 |
| `shared/vector_store/factory.py` | `qdrant` 분기 추가 |
| `tests/shared/test_config.py` | Qdrant 기본값 및 환경변수 테스트 추가 |
| `tests/shared/test_vector_store.py` | `QdrantStore` 단위 테스트 추가 |

---

## Task 1: requirements.txt에 qdrant-client 추가

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: qdrant-client 추가**

`requirements.txt` 파일에서 `chromadb>=0.5.0` 아래 줄에 추가:

```
qdrant-client>=1.7.0
```

최종 파일:
```
openai>=1.0.0
anthropic>=0.20.0
sentence-transformers>=2.0.0
chromadb>=0.5.0
qdrant-client>=1.7.0
python-dotenv>=1.0.0
langchain>=0.3.0
langchain-core>=0.3.0
langchain-openai>=0.2.0
langchain-community>=0.3.0
langgraph>=0.2.0
pyyaml>=6.0
pytest>=8.0.0
pytest-mock>=3.0.0
```

- [ ] **Step 2: 패키지 설치 확인**

```bash
pip install qdrant-client>=1.7.0
python -c "import qdrant_client; print(qdrant_client.__version__)"
```

Expected: 버전 출력 (예: `1.9.1`)

- [ ] **Step 3: 커밋**

```bash
git add requirements.txt
git commit -m "chore: add qdrant-client dependency"
```

---

## Task 2: Config에 Qdrant 설정 필드 추가

**Files:**
- Modify: `shared/config.py`
- Modify: `tests/shared/test_config.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/shared/test_config.py`에 아래 두 테스트를 추가한다 (파일 끝에 추가):

```python
def test_load_config_qdrant_defaults(monkeypatch):
    monkeypatch.delenv("QDRANT_URL", raising=False)
    monkeypatch.delenv("QDRANT_API_KEY", raising=False)
    monkeypatch.delenv("QDRANT_COLLECTION", raising=False)

    config = load_config()

    assert config.qdrant_url == ""
    assert config.qdrant_api_key == ""
    assert config.qdrant_collection == "documents"


def test_load_config_qdrant_from_env(monkeypatch):
    monkeypatch.setenv("QDRANT_URL", "https://xyz.qdrant.io:6333")
    monkeypatch.setenv("QDRANT_API_KEY", "test-api-key")
    monkeypatch.setenv("QDRANT_COLLECTION", "my-collection")

    config = load_config()

    assert config.qdrant_url == "https://xyz.qdrant.io:6333"
    assert config.qdrant_api_key == "test-api-key"
    assert config.qdrant_collection == "my-collection"
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/shared/test_config.py::test_load_config_qdrant_defaults -v
```

Expected: FAIL — `Config` has no attribute `qdrant_url`

- [ ] **Step 3: Config 구현 수정**

`shared/config.py`를 아래와 같이 교체한다:

```python
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    llm_provider: str
    llm_model: str
    openai_api_key: str
    anthropic_api_key: str
    vector_store: str
    chroma_mode: str
    chroma_path: str
    embedding_model: str
    qdrant_url: str
    qdrant_api_key: str
    qdrant_collection: str


def load_config() -> Config:
    return Config(
        llm_provider=os.getenv("LLM_PROVIDER", "openai"),
        llm_model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        vector_store=os.getenv("VECTOR_STORE", "chroma"),
        chroma_mode=os.getenv("CHROMA_MODE", "embedded"),
        chroma_path=os.getenv("CHROMA_PATH", "./.chroma"),
        embedding_model=os.getenv(
            "EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2"
        ),
        qdrant_url=os.getenv("QDRANT_URL", ""),
        qdrant_api_key=os.getenv("QDRANT_API_KEY", ""),
        qdrant_collection=os.getenv("QDRANT_COLLECTION", "documents"),
    )
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/shared/test_config.py -v
```

Expected: 모든 테스트 PASS (기존 4개 + 신규 2개)

- [ ] **Step 5: 커밋**

```bash
git add shared/config.py tests/shared/test_config.py
git commit -m "feat: add Qdrant config fields (qdrant_url, qdrant_api_key, qdrant_collection)"
```

---

## Task 3: QdrantStore 구현 (TDD)

**Files:**
- Create: `shared/vector_store/qdrant_store.py`
- Modify: `tests/shared/test_vector_store.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/shared/test_vector_store.py` 파일 상단 import에 아래를 추가:

```python
from unittest.mock import MagicMock, patch
```

파일 끝에 아래 테스트들을 추가:

```python
@pytest.fixture
def mock_qdrant_client():
    with patch("shared.vector_store.qdrant_store.QdrantClient") as mock_cls:
        mock_instance = MagicMock()
        # 기본적으로 collection이 없는 상태
        mock_instance.get_collections.return_value.collections = []
        mock_cls.return_value = mock_instance
        yield mock_instance


def test_qdrant_store_count_when_empty(mock_qdrant_client):
    from shared.vector_store.qdrant_store import QdrantStore

    store = QdrantStore(url="https://test.qdrant.io", api_key="key", collection="docs")
    assert store.count() == 0


def test_qdrant_store_add_creates_collection_and_upserts(mock_qdrant_client):
    from shared.vector_store.qdrant_store import QdrantStore

    store = QdrantStore(url="https://test.qdrant.io", api_key="key", collection="docs")
    chunks = [Chunk(text="안녕하세요", source="doc.md", chunk_id="c1")]
    embeddings = [[0.1, 0.2, 0.3]]

    store.add(chunks, embeddings)

    mock_qdrant_client.create_collection.assert_called_once()
    call_kwargs = mock_qdrant_client.create_collection.call_args.kwargs
    assert call_kwargs["collection_name"] == "docs"

    mock_qdrant_client.upsert.assert_called_once()
    upsert_kwargs = mock_qdrant_client.upsert.call_args.kwargs
    assert upsert_kwargs["collection_name"] == "docs"
    assert len(upsert_kwargs["points"]) == 1


def test_qdrant_store_add_skips_create_if_collection_exists(mock_qdrant_client):
    from shared.vector_store.qdrant_store import QdrantStore

    existing = MagicMock()
    existing.name = "docs"
    mock_qdrant_client.get_collections.return_value.collections = [existing]

    store = QdrantStore(url="https://test.qdrant.io", api_key="key", collection="docs")
    chunks = [Chunk(text="테스트", source="a.md", chunk_id="c2")]
    store.add(chunks, [[0.1, 0.2, 0.3]])

    mock_qdrant_client.create_collection.assert_not_called()


def test_qdrant_store_search_returns_results(mock_qdrant_client):
    from shared.vector_store.qdrant_store import QdrantStore

    hit = MagicMock()
    hit.score = 0.95
    hit.payload = {"text": "연차는 15일입니다", "source": "vacation.md", "chunk_id": "c1"}
    mock_qdrant_client.search.return_value = [hit]

    store = QdrantStore(url="https://test.qdrant.io", api_key="key", collection="docs")
    results = store.search(query_embedding=[1.0, 0.0, 0.0], top_k=1)

    assert len(results) == 1
    assert results[0].chunk.text == "연차는 15일입니다"
    assert results[0].chunk.source == "vacation.md"
    assert results[0].chunk.chunk_id == "c1"
    assert results[0].score == 0.95

    mock_qdrant_client.search.assert_called_once_with(
        collection_name="docs",
        query_vector=[1.0, 0.0, 0.0],
        limit=1,
    )


def test_qdrant_store_count_after_add(mock_qdrant_client):
    from shared.vector_store.qdrant_store import QdrantStore

    existing = MagicMock()
    existing.name = "docs"
    mock_qdrant_client.get_collections.return_value.collections = [existing]
    mock_qdrant_client.count.return_value.count = 3

    store = QdrantStore(url="https://test.qdrant.io", api_key="key", collection="docs")
    assert store.count() == 3

    mock_qdrant_client.count.assert_called_once_with(collection_name="docs")
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/shared/test_vector_store.py::test_qdrant_store_count_when_empty -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'shared.vector_store.qdrant_store'`

- [ ] **Step 3: QdrantStore 구현**

`shared/vector_store/qdrant_store.py` 파일을 신규 생성:

```python
import uuid
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from shared.models import Chunk, SearchResult
from shared.vector_store.base import VectorStore


class QdrantStore(VectorStore):
    def __init__(self, url: str, api_key: str, collection: str) -> None:
        self._client = QdrantClient(url=url, api_key=api_key)
        self._collection = collection

    def add(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        existing = [c.name for c in self._client.get_collections().collections]
        if self._collection not in existing:
            self._client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(
                    size=len(embeddings[0]), distance=Distance.COSINE
                ),
            )
        points = [
            PointStruct(
                id=uuid.uuid5(uuid.NAMESPACE_DNS, c.chunk_id),
                vector=emb,
                payload={"text": c.text, "source": c.source, "chunk_id": c.chunk_id},
            )
            for c, emb in zip(chunks, embeddings)
        ]
        self._client.upsert(collection_name=self._collection, points=points)

    def search(
        self, query_embedding: list[float], top_k: int = 5
    ) -> list[SearchResult]:
        hits = self._client.search(
            collection_name=self._collection,
            query_vector=query_embedding,
            limit=top_k,
        )
        return [
            SearchResult(
                chunk=Chunk(
                    text=h.payload["text"],
                    source=h.payload["source"],
                    chunk_id=h.payload["chunk_id"],
                ),
                score=h.score,
            )
            for h in hits
        ]

    def count(self) -> int:
        existing = [c.name for c in self._client.get_collections().collections]
        if self._collection not in existing:
            return 0
        return self._client.count(collection_name=self._collection).count
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/shared/test_vector_store.py -v
```

Expected: 모든 테스트 PASS (기존 5개 + 신규 5개)

- [ ] **Step 5: 커밋**

```bash
git add shared/vector_store/qdrant_store.py tests/shared/test_vector_store.py
git commit -m "feat: add QdrantStore implementing VectorStore ABC"
```

---

## Task 4: factory.py에 Qdrant 분기 추가

**Files:**
- Modify: `shared/vector_store/factory.py`
- Modify: `tests/shared/test_vector_store.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/shared/test_vector_store.py` 파일 상단 import 블록에 추가:

```python
from shared.vector_store.factory import create_vector_store
from shared.config import Config
```

파일 끝에 추가:

```python
def test_factory_creates_qdrant_store(mock_qdrant_client):
    from shared.vector_store.qdrant_store import QdrantStore

    config = Config(
        llm_provider="openai",
        llm_model="gpt-4o-mini",
        openai_api_key="",
        anthropic_api_key="",
        vector_store="qdrant",
        chroma_mode="embedded",
        chroma_path="./.chroma",
        embedding_model="paraphrase-multilingual-MiniLM-L12-v2",
        qdrant_url="https://test.qdrant.io",
        qdrant_api_key="test-key",
        qdrant_collection="my-col",
    )

    store = create_vector_store(config)

    assert isinstance(store, QdrantStore)


def test_factory_creates_chroma_store_by_default(tmp_path):
    from shared.vector_store.chroma_store import ChromaStore

    config = Config(
        llm_provider="openai",
        llm_model="gpt-4o-mini",
        openai_api_key="",
        anthropic_api_key="",
        vector_store="chroma",
        chroma_mode="embedded",
        chroma_path=str(tmp_path),
        embedding_model="paraphrase-multilingual-MiniLM-L12-v2",
        qdrant_url="",
        qdrant_api_key="",
        qdrant_collection="documents",
    )

    store = create_vector_store(config)

    assert isinstance(store, ChromaStore)
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/shared/test_vector_store.py::test_factory_creates_qdrant_store -v
```

Expected: FAIL — factory returns `ChromaStore` instead of `QdrantStore`

- [ ] **Step 3: factory.py 구현 수정**

`shared/vector_store/factory.py`를 아래로 교체:

```python
from shared.config import Config
from shared.vector_store.base import VectorStore
from shared.vector_store.chroma_store import ChromaStore
from shared.vector_store.qdrant_store import QdrantStore


def create_vector_store(config: Config) -> VectorStore:
    if config.vector_store == "qdrant":
        return QdrantStore(
            url=config.qdrant_url,
            api_key=config.qdrant_api_key,
            collection=config.qdrant_collection,
        )
    return ChromaStore(path=config.chroma_path, mode=config.chroma_mode)
```

- [ ] **Step 4: 전체 테스트 통과 확인**

```bash
pytest tests/shared/ -v
```

Expected: 모든 테스트 PASS

- [ ] **Step 5: 커밋**

```bash
git add shared/vector_store/factory.py tests/shared/test_vector_store.py
git commit -m "feat: factory supports VECTOR_STORE=qdrant via QdrantStore"
```

---

## Self-Review

### Spec coverage 체크
- [x] `QdrantStore` 구현 (`add`, `search`, `count`) → Task 3
- [x] `Config`에 `qdrant_url`, `qdrant_api_key`, `qdrant_collection` 추가 → Task 2
- [x] `factory.py` Qdrant 분기 → Task 4
- [x] `requirements.txt` → Task 1
- [x] Qdrant Cloud 환경변수 → Task 2
- [x] mock 기반 단위 테스트 → Task 3, 4

### 타입 일관성
- `QdrantStore(url, api_key, collection)` 생성자 → factory에서 동일 인자 전달 ✓
- `SearchResult(chunk=Chunk(...), score=h.score)` → `VectorStore.search` 반환 타입 일치 ✓
- `Config.qdrant_*` 필드명 → factory에서 동일 속성명 참조 ✓
