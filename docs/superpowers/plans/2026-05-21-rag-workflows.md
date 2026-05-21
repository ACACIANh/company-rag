# RAG Workflows Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 동일한 회사 내부 문서를 대상으로 4가지 오케스트레이션 방식(Simple / LangChain LCEL / LangChain Agent / LangGraph)의 RAG Q&A를 단일 CLI로 비교 실행한다.

**Architecture:** `shared/`에 LLM·VectorStore·Indexer·Retriever를 ABC+Factory 패턴으로 구현하고, `workflows/` 하위 4개 디렉토리에서 오케스트레이션만 다르게 구현한다. 번호로 시작하는 디렉토리명(`01_simple` 등)은 Python 식별자가 아니므로 `main.py`에서 `importlib.util.spec_from_file_location`으로 파일 경로 기반 동적 로드를 사용한다.

**Tech Stack:** Python 3.11+, openai, anthropic, sentence-transformers, chromadb, langchain, langchain-openai, langchain-community, langgraph, pytest, pytest-mock, pyyaml

---

## File Map

```
company-agent/
├── docs/                          ← 참고 프로젝트에서 복사
├── .env.example
├── .gitignore
├── requirements.txt
├── main.py                        ← 단일 CLI 진입점
│
├── shared/
│   ├── __init__.py
│   ├── models.py                  ← Chunk, SearchResult, Answer DTOs
│   ├── config.py                  ← Config dataclass + load_config()
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── base.py                ← LLMClient ABC
│   │   ├── openai_client.py
│   │   ├── anthropic_client.py
│   │   ├── factory.py
│   │   └── adapters/
│   │       ├── __init__.py
│   │       └── langchain_adapter.py  ← LLMClient → LangChain BaseLLM
│   ├── vector_store/
│   │   ├── __init__.py
│   │   ├── base.py                ← VectorStore ABC
│   │   ├── chroma_store.py
│   │   ├── factory.py
│   │   └── adapters/
│   │       ├── __init__.py
│   │       └── langchain_retriever.py  ← VectorStore → BaseRetriever
│   ├── indexer/
│   │   ├── __init__.py
│   │   └── indexer.py
│   └── retriever/
│       ├── __init__.py
│       ├── embedding.py
│       └── retriever.py
│
├── evals/
│   ├── __init__.py
│   ├── questions.yaml
│   └── runner.py
│
├── workflows/
│   ├── 01_simple/
│   │   ├── __init__.py
│   │   └── qa.py
│   ├── 02_1_langchain_basic/
│   │   ├── __init__.py
│   │   ├── chain/
│   │   │   ├── __init__.py
│   │   │   └── chain.py
│   │   └── qa.py
│   ├── 02_2_langchain_agentic/
│   │   ├── __init__.py
│   │   ├── tools/
│   │   │   ├── __init__.py
│   │   │   └── rag_tool.py
│   │   ├── agent/
│   │   │   ├── __init__.py
│   │   │   └── agent.py
│   │   └── qa.py
│   └── 03_langgraph/
│       ├── __init__.py
│       ├── nodes/
│       │   ├── __init__.py
│       │   ├── router.py
│       │   ├── rag.py
│       │   └── direct.py
│       ├── graph/
│       │   ├── __init__.py
│       │   └── graph.py
│       └── qa.py
│
└── tests/
    ├── __init__.py
    ├── shared/
    │   ├── __init__.py
    │   ├── test_models.py
    │   ├── test_config.py
    │   ├── test_llm.py
    │   ├── test_vector_store.py
    │   ├── test_retriever.py
    │   ├── test_indexer.py
    │   └── test_adapters.py
    └── workflows/
        ├── __init__.py
        ├── test_01_simple.py
        ├── test_02_1_langchain.py
        ├── test_02_2_agentic.py
        └── test_03_langgraph.py
```

---

## Task 1: 프로젝트 스캐폴딩

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `.gitignore`
- Create: 모든 `__init__.py` 파일들
- Copy: `docs/` (참고 프로젝트에서)

- [ ] **Step 1: conftest.py 생성 (pytest sys.path 설정)**

```python
# conftest.py  ← 프로젝트 루트에 생성
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
```

저장: `conftest.py`

- [ ] **Step 2: docs 복사 및 디렉토리 생성**

```bash
cp -r /Users/acacian/vscode/ai-agent/company-agent/rag-day1/docs /Users/acacian/vscode/company-agent/
mkdir -p shared/llm/adapters shared/vector_store/adapters shared/indexer shared/retriever
mkdir -p workflows/01_simple workflows/02_1_langchain_basic/chain
mkdir -p workflows/02_2_langchain_agentic/tools workflows/02_2_langchain_agentic/agent
mkdir -p workflows/03_langgraph/nodes workflows/03_langgraph/graph
mkdir -p evals tests/shared tests/workflows
touch shared/__init__.py shared/llm/__init__.py shared/llm/adapters/__init__.py
touch shared/vector_store/__init__.py shared/vector_store/adapters/__init__.py
touch shared/indexer/__init__.py shared/retriever/__init__.py
touch workflows/01_simple/__init__.py workflows/02_1_langchain_basic/__init__.py
touch workflows/02_1_langchain_basic/chain/__init__.py
touch workflows/02_2_langchain_agentic/__init__.py
touch workflows/02_2_langchain_agentic/tools/__init__.py workflows/02_2_langchain_agentic/agent/__init__.py
touch workflows/03_langgraph/__init__.py workflows/03_langgraph/nodes/__init__.py
touch workflows/03_langgraph/graph/__init__.py
touch evals/__init__.py tests/__init__.py tests/shared/__init__.py tests/workflows/__init__.py
```

- [ ] **Step 2: requirements.txt 작성**

```
openai>=1.0.0
anthropic>=0.20.0
sentence-transformers>=2.0.0
chromadb>=0.5.0
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

저장: `requirements.txt`

- [ ] **Step 3: .env.example 작성**

```
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

VECTOR_STORE=chroma
CHROMA_MODE=embedded
CHROMA_PATH=./.chroma

EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2
```

저장: `.env.example`

- [ ] **Step 4: .gitignore 작성**

```
.env
.chroma/
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
dist/
.venv/
venv/
```

저장: `.gitignore`

- [ ] **Step 6: 의존성 설치 확인**

```bash
pip install -r requirements.txt
```

Expected: 오류 없이 설치 완료

- [ ] **Step 7: 커밋**

```bash
git init
git add .
git commit -m "chore: project scaffolding — directories, requirements, docs"
```

---

## Task 2: shared/models.py

**Files:**
- Create: `shared/models.py`
- Create: `tests/shared/test_models.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/shared/test_models.py
from shared.models import Chunk, SearchResult, Answer


def test_chunk_fields():
    chunk = Chunk(text="hello", source="doc.md", chunk_id="abc-123")
    assert chunk.text == "hello"
    assert chunk.source == "doc.md"
    assert chunk.chunk_id == "abc-123"


def test_search_result_fields():
    chunk = Chunk(text="hello", source="doc.md", chunk_id="abc-123")
    result = SearchResult(chunk=chunk, score=0.9)
    assert result.chunk is chunk
    assert result.score == 0.9


def test_answer_defaults():
    answer = Answer(text="답변", sources=["doc.md"])
    assert answer.text == "답변"
    assert answer.sources == ["doc.md"]
    assert answer.trace is None


def test_answer_with_trace():
    trace = [{"step": "retrieve", "count": 5}]
    answer = Answer(text="답변", sources=["doc.md"], trace=trace)
    assert answer.trace == trace
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/shared/test_models.py -v
```

Expected: `ModuleNotFoundError: No module named 'shared.models'`

- [ ] **Step 3: shared/models.py 구현**

```python
from dataclasses import dataclass, field


@dataclass
class Chunk:
    text: str
    source: str
    chunk_id: str


@dataclass
class SearchResult:
    chunk: Chunk
    score: float


@dataclass
class Answer:
    text: str
    sources: list[str]
    trace: list[dict] | None = None
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/shared/test_models.py -v
```

Expected: 4개 PASSED

- [ ] **Step 5: 커밋**

```bash
git add shared/models.py tests/shared/test_models.py
git commit -m "feat: shared models — Chunk, SearchResult, Answer DTOs"
```

---

## Task 3: shared/config.py

**Files:**
- Create: `shared/config.py`
- Create: `tests/shared/test_config.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/shared/test_config.py
import os
import pytest
from shared.config import Config, load_config


def test_load_config_defaults(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("VECTOR_STORE", raising=False)
    monkeypatch.delenv("CHROMA_MODE", raising=False)
    monkeypatch.delenv("CHROMA_PATH", raising=False)
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)

    config = load_config()

    assert config.llm_provider == "openai"
    assert config.llm_model == "gpt-4o-mini"
    assert config.vector_store == "chroma"
    assert config.chroma_mode == "embedded"
    assert config.chroma_path == "./.chroma"


def test_load_config_from_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_MODEL", "claude-3-haiku-20240307")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    config = load_config()

    assert config.llm_provider == "anthropic"
    assert config.llm_model == "claude-3-haiku-20240307"
    assert config.anthropic_api_key == "sk-ant-test"
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/shared/test_config.py -v
```

Expected: `ModuleNotFoundError: No module named 'shared.config'`

- [ ] **Step 3: shared/config.py 구현**

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
    )
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/shared/test_config.py -v
```

Expected: 2개 PASSED

- [ ] **Step 5: 커밋**

```bash
git add shared/config.py tests/shared/test_config.py
git commit -m "feat: shared config — load_config() from env vars"
```

---

## Task 4: shared/llm/ — ABC, 클라이언트, 팩토리

**Files:**
- Create: `shared/llm/base.py`
- Create: `shared/llm/openai_client.py`
- Create: `shared/llm/anthropic_client.py`
- Create: `shared/llm/factory.py`
- Create: `tests/shared/test_llm.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/shared/test_llm.py
import pytest
from unittest.mock import MagicMock, patch
from shared.config import Config
from shared.llm.base import LLMClient
from shared.llm.openai_client import OpenAIClient
from shared.llm.anthropic_client import AnthropicClient
from shared.llm.factory import create_llm


def test_llm_client_is_abstract():
    with pytest.raises(TypeError):
        LLMClient()


def test_openai_client_complete(mocker):
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "테스트 답변"
    mocker.patch("shared.llm.openai_client.OpenAI")

    client = OpenAIClient(model="gpt-4o-mini", api_key="test-key")
    client._client.chat.completions.create.return_value = mock_response

    result = client.complete("테스트 질문")

    assert result == "테스트 답변"


def test_anthropic_client_complete(mocker):
    mock_response = MagicMock()
    mock_response.content[0].text = "테스트 답변"
    mocker.patch("shared.llm.anthropic_client.anthropic.Anthropic")

    client = AnthropicClient(model="claude-3-haiku-20240307", api_key="test-key")
    client._client.messages.create.return_value = mock_response

    result = client.complete("테스트 질문")

    assert result == "테스트 답변"


def test_factory_creates_openai_by_default(monkeypatch, mocker):
    mocker.patch("shared.llm.openai_client.OpenAI")
    config = Config(
        llm_provider="openai", llm_model="gpt-4o-mini",
        openai_api_key="sk-test", anthropic_api_key="",
        vector_store="chroma", chroma_mode="embedded",
        chroma_path=".chroma", embedding_model="test-model",
    )
    llm = create_llm(config)
    assert isinstance(llm, OpenAIClient)


def test_factory_creates_anthropic(mocker):
    mocker.patch("shared.llm.anthropic_client.anthropic.Anthropic")
    config = Config(
        llm_provider="anthropic", llm_model="claude-3-haiku-20240307",
        openai_api_key="", anthropic_api_key="sk-ant-test",
        vector_store="chroma", chroma_mode="embedded",
        chroma_path=".chroma", embedding_model="test-model",
    )
    llm = create_llm(config)
    assert isinstance(llm, AnthropicClient)
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/shared/test_llm.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: shared/llm/base.py 구현**

```python
from abc import ABC, abstractmethod


class LLMClient(ABC):
    @abstractmethod
    def complete(self, prompt: str) -> str:
        ...
```

- [ ] **Step 4: shared/llm/openai_client.py 구현**

```python
from openai import OpenAI
from shared.llm.base import LLMClient


class OpenAIClient(LLMClient):
    def __init__(self, model: str, api_key: str) -> None:
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def complete(self, prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content
```

- [ ] **Step 5: shared/llm/anthropic_client.py 구현**

```python
import anthropic
from shared.llm.base import LLMClient


class AnthropicClient(LLMClient):
    def __init__(self, model: str, api_key: str) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def complete(self, prompt: str) -> str:
        message = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text
```

- [ ] **Step 6: shared/llm/factory.py 구현**

```python
from shared.config import Config
from shared.llm.base import LLMClient
from shared.llm.anthropic_client import AnthropicClient
from shared.llm.openai_client import OpenAIClient


def create_llm(config: Config) -> LLMClient:
    if config.llm_provider == "anthropic":
        return AnthropicClient(
            model=config.llm_model, api_key=config.anthropic_api_key
        )
    return OpenAIClient(model=config.llm_model, api_key=config.openai_api_key)
```

- [ ] **Step 7: 테스트 통과 확인**

```bash
pytest tests/shared/test_llm.py -v
```

Expected: 5개 PASSED

- [ ] **Step 8: 커밋**

```bash
git add shared/llm/ tests/shared/test_llm.py
git commit -m "feat: shared LLM — OpenAI/Anthropic clients with ABC+Factory"
```

---

## Task 5: shared/vector_store/ — ABC, ChromaStore, 팩토리

**Files:**
- Create: `shared/vector_store/base.py`
- Create: `shared/vector_store/chroma_store.py`
- Create: `shared/vector_store/factory.py`
- Create: `tests/shared/test_vector_store.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/shared/test_vector_store.py
import pytest
import tempfile
from shared.models import Chunk
from shared.vector_store.base import VectorStore
from shared.vector_store.chroma_store import ChromaStore


def test_vector_store_is_abstract():
    with pytest.raises(TypeError):
        VectorStore()


@pytest.fixture
def chroma_store(tmp_path):
    return ChromaStore(path=str(tmp_path), mode="embedded")


def test_chroma_store_initially_empty(chroma_store):
    assert chroma_store.count() == 0


def test_chroma_store_add_and_count(chroma_store):
    chunks = [Chunk(text="안녕하세요", source="doc.md", chunk_id="c1")]
    embeddings = [[0.1, 0.2, 0.3]]
    chroma_store.add(chunks, embeddings)
    assert chroma_store.count() == 1


def test_chroma_store_search(chroma_store):
    chunks = [
        Chunk(text="연차는 15일입니다", source="vacation.md", chunk_id="c1"),
        Chunk(text="점심시간은 1시간입니다", source="policy.md", chunk_id="c2"),
    ]
    embeddings = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    chroma_store.add(chunks, embeddings)

    results = chroma_store.search(query_embedding=[1.0, 0.0, 0.0], top_k=1)

    assert len(results) == 1
    assert results[0].chunk.source == "vacation.md"
    assert results[0].score >= 0
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/shared/test_vector_store.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: shared/vector_store/base.py 구현**

```python
from abc import ABC, abstractmethod
from shared.models import Chunk, SearchResult


class VectorStore(ABC):
    @abstractmethod
    def add(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        ...

    @abstractmethod
    def search(
        self, query_embedding: list[float], top_k: int = 5
    ) -> list[SearchResult]:
        ...

    @abstractmethod
    def count(self) -> int:
        ...
```

- [ ] **Step 4: shared/vector_store/chroma_store.py 구현**

```python
import chromadb
from shared.models import Chunk, SearchResult
from shared.vector_store.base import VectorStore


class ChromaStore(VectorStore):
    def __init__(
        self,
        path: str,
        mode: str = "embedded",
        host: str = "localhost",
        port: int = 8000,
    ) -> None:
        if mode == "http":
            self._client = chromadb.HttpClient(host=host, port=port)
        else:
            self._client = chromadb.PersistentClient(path=path)
        self._collection = self._client.get_or_create_collection("documents")

    def add(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        self._collection.add(
            ids=[c.chunk_id for c in chunks],
            documents=[c.text for c in chunks],
            embeddings=embeddings,
            metadatas=[{"source": c.source} for c in chunks],
        )

    def search(
        self, query_embedding: list[float], top_k: int = 5
    ) -> list[SearchResult]:
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, self._collection.count()),
        )
        output = []
        for i, doc in enumerate(results["documents"][0]):
            chunk = Chunk(
                text=doc,
                source=results["metadatas"][0][i]["source"],
                chunk_id=results["ids"][0][i],
            )
            score = 1.0 - results["distances"][0][i]
            output.append(SearchResult(chunk=chunk, score=score))
        return output

    def count(self) -> int:
        return self._collection.count()
```

- [ ] **Step 5: shared/vector_store/factory.py 구현**

```python
from shared.config import Config
from shared.vector_store.base import VectorStore
from shared.vector_store.chroma_store import ChromaStore


def create_vector_store(config: Config) -> VectorStore:
    return ChromaStore(path=config.chroma_path, mode=config.chroma_mode)
```

- [ ] **Step 6: 테스트 통과 확인**

```bash
pytest tests/shared/test_vector_store.py -v
```

Expected: 5개 PASSED

- [ ] **Step 7: 커밋**

```bash
git add shared/vector_store/ tests/shared/test_vector_store.py
git commit -m "feat: shared VectorStore — ChromaStore with ABC+Factory"
```

---

## Task 6: shared/retriever/ — EmbeddingService + Retriever

**Files:**
- Create: `shared/retriever/embedding.py`
- Create: `shared/retriever/retriever.py`
- Create: `tests/shared/test_retriever.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/shared/test_retriever.py
import pytest
from unittest.mock import MagicMock
from shared.models import Chunk, SearchResult
from shared.retriever.retriever import Retriever


@pytest.fixture
def mock_store():
    store = MagicMock()
    store.search.return_value = [
        SearchResult(
            chunk=Chunk(text="연차 15일", source="vacation.md", chunk_id="c1"),
            score=0.9,
        )
    ]
    return store


@pytest.fixture
def mock_embedder():
    embedder = MagicMock()
    embedder.embed.return_value = [0.1, 0.2, 0.3]
    return embedder


def test_retriever_calls_embed_and_search(mock_store, mock_embedder):
    retriever = Retriever(vector_store=mock_store, embedding_service=mock_embedder)

    results = retriever.retrieve("연차 며칠이야", top_k=3)

    mock_embedder.embed.assert_called_once_with("연차 며칠이야")
    mock_store.search.assert_called_once_with([0.1, 0.2, 0.3], top_k=3)
    assert len(results) == 1
    assert results[0].chunk.source == "vacation.md"
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/shared/test_retriever.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: shared/retriever/embedding.py 구현**

```python
from sentence_transformers import SentenceTransformer


class EmbeddingService:
    def __init__(self, model_name: str) -> None:
        self._model = SentenceTransformer(model_name)

    def embed(self, text: str) -> list[float]:
        return self._model.encode(text).tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts).tolist()
```

- [ ] **Step 4: shared/retriever/retriever.py 구현**

```python
from shared.models import SearchResult
from shared.retriever.embedding import EmbeddingService
from shared.vector_store.base import VectorStore


class Retriever:
    def __init__(
        self, vector_store: VectorStore, embedding_service: EmbeddingService
    ) -> None:
        self._store = vector_store
        self._embedder = embedding_service

    def retrieve(self, query: str, top_k: int = 5) -> list[SearchResult]:
        embedding = self._embedder.embed(query)
        return self._store.search(embedding, top_k=top_k)
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
pytest tests/shared/test_retriever.py -v
```

Expected: 1개 PASSED

- [ ] **Step 6: 커밋**

```bash
git add shared/retriever/ tests/shared/test_retriever.py
git commit -m "feat: shared retriever — EmbeddingService + Retriever"
```

---

## Task 7: shared/indexer/indexer.py

**Files:**
- Create: `shared/indexer/indexer.py`
- Create: `tests/shared/test_indexer.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/shared/test_indexer.py
import os
import pytest
from unittest.mock import MagicMock
from shared.indexer.indexer import Indexer


@pytest.fixture
def mock_store():
    store = MagicMock()
    store.add = MagicMock()
    return store


@pytest.fixture
def mock_embedder():
    embedder = MagicMock()
    embedder.embed_batch.return_value = [[0.1, 0.2], [0.3, 0.4]]
    return embedder


@pytest.fixture
def docs_dir(tmp_path):
    (tmp_path / "policy.md").write_text("연차는 15일입니다. 모든 직원에게 적용됩니다.")
    return str(tmp_path)


def test_indexer_indexes_markdown_files(mock_store, mock_embedder, docs_dir):
    indexer = Indexer(
        vector_store=mock_store,
        embedding_service=mock_embedder,
        chunk_size=100,
        chunk_overlap=10,
    )

    count = indexer.index_directory(docs_dir)

    assert count > 0
    mock_store.add.assert_called_once()


def test_indexer_ignores_non_md_files(mock_store, mock_embedder, tmp_path):
    (tmp_path / "README.txt").write_text("이 파일은 무시됩니다.")
    mock_embedder.embed_batch.return_value = []
    indexer = Indexer(
        vector_store=mock_store, embedding_service=mock_embedder
    )

    count = indexer.index_directory(str(tmp_path))

    assert count == 0
    mock_store.add.assert_not_called()
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/shared/test_indexer.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: shared/indexer/indexer.py 구현**

```python
import os
import uuid
from shared.models import Chunk
from shared.retriever.embedding import EmbeddingService
from shared.vector_store.base import VectorStore


class Indexer:
    def __init__(
        self,
        vector_store: VectorStore,
        embedding_service: EmbeddingService,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> None:
        self._store = vector_store
        self._embedder = embedding_service
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    def index_directory(self, docs_path: str) -> int:
        chunks = []
        for filename in sorted(os.listdir(docs_path)):
            if not filename.endswith(".md"):
                continue
            filepath = os.path.join(docs_path, filename)
            with open(filepath, encoding="utf-8") as f:
                content = f.read()
            chunks.extend(self._chunk_text(content, filename))

        if not chunks:
            return 0

        embeddings = self._embedder.embed_batch([c.text for c in chunks])
        self._store.add(chunks, embeddings)
        return len(chunks)

    def _chunk_text(self, text: str, source: str) -> list[Chunk]:
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + self._chunk_size, len(text))
            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append(
                    Chunk(
                        text=chunk_text,
                        source=source,
                        chunk_id=str(uuid.uuid4()),
                    )
                )
            start += self._chunk_size - self._chunk_overlap
        return chunks
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/shared/test_indexer.py -v
```

Expected: 2개 PASSED

- [ ] **Step 5: 커밋**

```bash
git add shared/indexer/ tests/shared/test_indexer.py
git commit -m "feat: shared indexer — markdown chunker with overlap"
```

---

## Task 8: LangChain 어댑터 — LLM + Retriever

**Files:**
- Create: `shared/llm/adapters/langchain_adapter.py`
- Create: `shared/vector_store/adapters/langchain_retriever.py`
- Create: `tests/shared/test_adapters.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/shared/test_adapters.py
import pytest
from unittest.mock import MagicMock
from langchain_core.documents import Document
from shared.llm.adapters.langchain_adapter import LangChainLLMAdapter
from shared.vector_store.adapters.langchain_retriever import LangChainRetrieverAdapter
from shared.models import Chunk, SearchResult


def test_langchain_llm_adapter_generates(mocker):
    mock_client = MagicMock()
    mock_client.complete.return_value = "테스트 답변"

    adapter = LangChainLLMAdapter(llm_client=mock_client)
    result = adapter.invoke("테스트 프롬프트")

    mock_client.complete.assert_called_once_with("테스트 프롬프트")
    assert "테스트 답변" in result


def test_langchain_retriever_adapter_returns_documents():
    mock_store = MagicMock()
    mock_store.search.return_value = [
        SearchResult(
            chunk=Chunk(text="연차 15일", source="vacation.md", chunk_id="c1"),
            score=0.9,
        )
    ]
    mock_embedder = MagicMock()
    mock_embedder.embed.return_value = [0.1, 0.2, 0.3]

    adapter = LangChainRetrieverAdapter(
        vector_store=mock_store, embedding_service=mock_embedder
    )
    docs = adapter.invoke("연차 며칠이야")

    assert len(docs) == 1
    assert isinstance(docs[0], Document)
    assert docs[0].page_content == "연차 15일"
    assert docs[0].metadata["source"] == "vacation.md"
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/shared/test_adapters.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: shared/llm/adapters/langchain_adapter.py 구현**

```python
from typing import Any
from langchain_core.language_models import BaseLLM
from langchain_core.outputs import Generation, LLMResult
from pydantic import Field
from shared.llm.base import LLMClient


class LangChainLLMAdapter(BaseLLM):
    """shared.LLMClient를 LangChain BaseLLM(Runnable)으로 래핑하는 어댑터."""

    llm_client: Any = Field(...)

    model_config = {"arbitrary_types_allowed": True}

    @property
    def _llm_type(self) -> str:
        return "shared_llm_adapter"

    def _generate(self, prompts: list[str], **kwargs: Any) -> LLMResult:
        return LLMResult(
            generations=[
                [Generation(text=self.llm_client.complete(p))] for p in prompts
            ]
        )
```

- [ ] **Step 4: shared/vector_store/adapters/langchain_retriever.py 구현**

```python
from typing import Any
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import Field
from shared.retriever.embedding import EmbeddingService
from shared.vector_store.base import VectorStore


class LangChainRetrieverAdapter(BaseRetriever):
    """shared.VectorStore를 LangChain BaseRetriever(Runnable)로 래핑하는 어댑터."""

    vector_store: Any = Field(...)
    embedding_service: Any = Field(...)
    top_k: int = 5

    model_config = {"arbitrary_types_allowed": True}

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        embedding = self.embedding_service.embed(query)
        results = self.vector_store.search(embedding, top_k=self.top_k)
        return [
            Document(
                page_content=r.chunk.text,
                metadata={"source": r.chunk.source, "score": r.score},
            )
            for r in results
        ]
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
pytest tests/shared/test_adapters.py -v
```

Expected: 2개 PASSED

- [ ] **Step 6: shared 전체 테스트**

```bash
pytest tests/shared/ -v
```

Expected: 전체 PASSED

- [ ] **Step 7: 커밋**

```bash
git add shared/llm/adapters/ shared/vector_store/adapters/ tests/shared/test_adapters.py
git commit -m "feat: LangChain adapters — LLMClient→BaseLLM, VectorStore→BaseRetriever"
```

---

## Task 9: workflows/01_simple/qa.py

**Files:**
- Create: `workflows/01_simple/qa.py`
- Create: `tests/workflows/test_01_simple.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/workflows/test_01_simple.py
import importlib.util
import os
import sys
import pytest
from unittest.mock import MagicMock
from shared.models import Answer, Chunk, SearchResult


def load_qa():
    path = os.path.join(os.path.dirname(__file__), "../../workflows/01_simple/qa.py")
    path = os.path.abspath(path)
    sys.path.insert(0, os.path.dirname(path))
    spec = importlib.util.spec_from_file_location("qa_01", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.path.pop(0)
    return module


def test_run_returns_answer(mocker):
    # load_qa() 먼저 → 이후 patch.object로 해당 모듈의 이름공간을 직접 패치
    qa = load_qa()

    mock_results = [
        SearchResult(
            chunk=Chunk(text="연차는 15일입니다", source="vacation.md", chunk_id="c1"),
            score=0.9,
        )
    ]
    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value = mock_results
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "연차는 15일입니다."

    mocker.patch.object(qa, "load_config")
    mocker.patch.object(qa, "EmbeddingService")
    mocker.patch.object(qa, "create_vector_store")
    mocker.patch.object(qa, "create_llm", return_value=mock_llm)
    mocker.patch.object(qa, "Retriever", return_value=mock_retriever)

    answer = qa.run("연차 며칠이야?")

    assert isinstance(answer, Answer)
    assert answer.text == "연차는 15일입니다."
    assert "vacation.md" in answer.sources
    assert answer.trace is None
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/workflows/test_01_simple.py -v
```

Expected: `FileNotFoundError` 또는 `ModuleNotFoundError`

- [ ] **Step 3: workflows/01_simple/qa.py 구현**

```python
from shared.config import load_config
from shared.llm.factory import create_llm
from shared.models import Answer
from shared.retriever.embedding import EmbeddingService
from shared.retriever.retriever import Retriever
from shared.vector_store.factory import create_vector_store

_PROMPT_TEMPLATE = """\
다음 문서를 참고하여 질문에 한국어로 답하세요.

문서:
{context}

질문: {question}
답변:"""


def run(question: str) -> Answer:
    config = load_config()
    embedder = EmbeddingService(config.embedding_model)
    store = create_vector_store(config)
    retriever = Retriever(store, embedder)
    llm = create_llm(config)

    results = retriever.retrieve(question, top_k=5)
    context = "\n\n".join(r.chunk.text for r in results)
    sources = list({r.chunk.source for r in results})

    prompt = _PROMPT_TEMPLATE.format(context=context, question=question)
    text = llm.complete(prompt)

    return Answer(text=text, sources=sources, trace=None)
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/workflows/test_01_simple.py -v
```

Expected: 1개 PASSED

- [ ] **Step 5: 커밋**

```bash
git add workflows/01_simple/ tests/workflows/test_01_simple.py
git commit -m "feat: 01_simple workflow — plain Python RAG pipeline"
```

---

## Task 10: workflows/02_1_langchain_basic/

**Files:**
- Create: `workflows/02_1_langchain_basic/chain/chain.py`
- Create: `workflows/02_1_langchain_basic/qa.py`
- Create: `tests/workflows/test_02_1_langchain.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/workflows/test_02_1_langchain.py
import importlib.util
import os
import sys
import pytest
from unittest.mock import MagicMock
from langchain_core.documents import Document
from shared.models import Answer


def load_qa():
    base = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../workflows/02_1_langchain_basic")
    )
    qa_path = os.path.join(base, "qa.py")
    sys.path.insert(0, base)
    spec = importlib.util.spec_from_file_location("qa_02_1", qa_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.path.pop(0)
    return module


def test_run_returns_answer(mocker):
    qa = load_qa()

    mock_docs = [
        Document(page_content="연차는 15일", metadata={"source": "vacation.md", "score": 0.9})
    ]
    mock_retriever_adapter = MagicMock()
    mock_retriever_adapter.invoke.return_value = mock_docs
    mock_llm_adapter = MagicMock()
    mock_chain = MagicMock()
    mock_chain.invoke.return_value = "연차는 15일입니다."

    mocker.patch.object(qa, "load_config")
    mocker.patch.object(qa, "EmbeddingService")
    mocker.patch.object(qa, "create_vector_store")
    mocker.patch.object(qa, "create_llm")
    mocker.patch.object(qa, "LangChainRetrieverAdapter", return_value=mock_retriever_adapter)
    mocker.patch.object(qa, "LangChainLLMAdapter", return_value=mock_llm_adapter)
    mocker.patch.object(qa, "build_chain", return_value=mock_chain)

    answer = qa.run("연차 며칠이야?")

    assert isinstance(answer, Answer)
    assert answer.text == "연차는 15일입니다."
    assert answer.trace is not None
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/workflows/test_02_1_langchain.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: workflows/02_1_langchain_basic/chain/chain.py 구현**

```python
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough

_PROMPT = PromptTemplate.from_template(
    """\
다음 문서를 참고하여 질문에 한국어로 답하세요.

문서:
{context}

질문: {question}
답변:"""
)


def _format_docs(docs) -> str:
    return "\n\n".join(d.page_content for d in docs)


def build_chain(retriever_adapter, llm_adapter):
    """LCEL 파이프라인: retriever | prompt | llm | parser"""
    return (
        {"context": retriever_adapter | _format_docs, "question": RunnablePassthrough()}
        | _PROMPT
        | llm_adapter
        | StrOutputParser()
    )
```

- [ ] **Step 4: workflows/02_1_langchain_basic/qa.py 구현**

```python
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from chain.chain import build_chain
from shared.config import load_config
from shared.llm.adapters.langchain_adapter import LangChainLLMAdapter
from shared.llm.factory import create_llm
from shared.models import Answer
from shared.retriever.embedding import EmbeddingService
from shared.vector_store.adapters.langchain_retriever import LangChainRetrieverAdapter
from shared.vector_store.factory import create_vector_store


def run(question: str) -> Answer:
    config = load_config()
    embedder = EmbeddingService(config.embedding_model)
    store = create_vector_store(config)
    llm_client = create_llm(config)

    retriever_adapter = LangChainRetrieverAdapter(
        vector_store=store, embedding_service=embedder
    )
    llm_adapter = LangChainLLMAdapter(llm_client=llm_client)
    chain = build_chain(retriever_adapter, llm_adapter)

    text = chain.invoke(question)

    docs = retriever_adapter.invoke(question)
    sources = list({d.metadata["source"] for d in docs})
    trace = [{"step": "lcel_chain", "output": text}]

    return Answer(text=text, sources=sources, trace=trace)
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
pytest tests/workflows/test_02_1_langchain.py -v
```

Expected: 1개 PASSED

- [ ] **Step 6: 커밋**

```bash
git add workflows/02_1_langchain_basic/ tests/workflows/test_02_1_langchain.py
git commit -m "feat: 02_1_langchain_basic workflow — LangChain LCEL chain with adapters"
```

---

## Task 11: workflows/02_2_langchain_agentic/

**Files:**
- Create: `workflows/02_2_langchain_agentic/tools/rag_tool.py`
- Create: `workflows/02_2_langchain_agentic/agent/agent.py`
- Create: `workflows/02_2_langchain_agentic/qa.py`
- Create: `tests/workflows/test_02_2_agentic.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/workflows/test_02_2_agentic.py
import importlib.util
import os
import sys
import pytest
from unittest.mock import MagicMock
from shared.models import Answer


def load_qa():
    base = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../workflows/02_2_langchain_agentic")
    )
    qa_path = os.path.join(base, "qa.py")
    sys.path.insert(0, base)
    spec = importlib.util.spec_from_file_location("qa_02_2", qa_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.path.pop(0)
    return module


def test_run_returns_answer_with_trace(mocker):
    qa = load_qa()

    mock_executor = MagicMock()
    mock_executor.invoke.return_value = {
        "output": "연차는 15일입니다.",
        "intermediate_steps": [
            (
                MagicMock(log="연차를 검색해야 한다", tool="search_company_docs"),
                "연차는 15일입니다.",
            )
        ],
    }

    mocker.patch.object(qa, "load_config")
    mocker.patch.object(qa, "EmbeddingService")
    mocker.patch.object(qa, "create_vector_store")
    mocker.patch.object(qa, "create_llm")
    mocker.patch.object(qa, "Retriever")
    mocker.patch.object(qa, "make_rag_tool")
    mocker.patch.object(qa, "LangChainLLMAdapter")
    mocker.patch.object(qa, "build_agent_executor", return_value=mock_executor)

    answer = qa.run("연차 며칠이야?")

    assert isinstance(answer, Answer)
    assert answer.text == "연차는 15일입니다."
    assert answer.trace is not None
    assert len(answer.trace) == 1
    assert answer.trace[0]["action"] == "search_company_docs"
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/workflows/test_02_2_agentic.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: workflows/02_2_langchain_agentic/tools/rag_tool.py 구현**

```python
from langchain_core.tools import tool
from shared.models import SearchResult


def make_rag_tool(retriever):
    """Retriever를 LangChain @tool로 래핑한다."""

    @tool
    def search_company_docs(query: str) -> str:
        """회사 내부 문서에서 정보를 검색합니다. 회사 정책, 규정, 가이드라인 질문에 사용하세요."""
        results: list[SearchResult] = retriever.retrieve(query, top_k=5)
        if not results:
            return "관련 문서를 찾을 수 없습니다."
        return "\n\n".join(
            f"[{r.chunk.source}] {r.chunk.text}" for r in results
        )

    return search_company_docs
```

- [ ] **Step 4: workflows/02_2_langchain_agentic/agent/agent.py 구현**

```python
from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate

_REACT_TEMPLATE = """\
당신은 회사 내부 문서 전문가입니다. 주어진 도구를 활용하여 질문에 답하세요.

사용 가능한 도구:
{tools}

형식:
Question: 답해야 할 질문
Thought: 어떻게 접근할지 생각합니다
Action: [{tool_names}] 중 하나
Action Input: 도구에 전달할 입력
Observation: 도구 실행 결과
... (Thought/Action/Action Input/Observation 반복 가능)
Thought: 최종 답변을 알았습니다
Final Answer: 최종 답변

시작!

Question: {input}
Thought:{agent_scratchpad}"""


def build_agent_executor(llm_adapter, tools: list) -> AgentExecutor:
    prompt = PromptTemplate.from_template(_REACT_TEMPLATE)
    agent = create_react_agent(llm_adapter, tools, prompt)
    return AgentExecutor(
        agent=agent,
        tools=tools,
        return_intermediate_steps=True,
        handle_parsing_errors=True,
        verbose=False,
    )
```

- [ ] **Step 5: workflows/02_2_langchain_agentic/qa.py 구현**

```python
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from agent.agent import build_agent_executor
from tools.rag_tool import make_rag_tool
from shared.config import load_config
from shared.llm.adapters.langchain_adapter import LangChainLLMAdapter
from shared.llm.factory import create_llm
from shared.models import Answer
from shared.retriever.embedding import EmbeddingService
from shared.retriever.retriever import Retriever
from shared.vector_store.factory import create_vector_store


def run(question: str) -> Answer:
    config = load_config()
    embedder = EmbeddingService(config.embedding_model)
    store = create_vector_store(config)
    llm_client = create_llm(config)

    retriever = Retriever(store, embedder)
    rag_tool = make_rag_tool(retriever)
    llm_adapter = LangChainLLMAdapter(llm_client=llm_client)
    executor = build_agent_executor(llm_adapter, [rag_tool])

    result = executor.invoke({"input": question})

    trace = [
        {
            "thought": step[0].log.strip(),
            "action": step[0].tool,
            "observation": str(step[1]),
        }
        for step in result.get("intermediate_steps", [])
    ]

    sources = list(
        {
            part.split("]")[0][1:]
            for step in result.get("intermediate_steps", [])
            for obs in [str(step[1])]
            for part in obs.split("\n\n")
            if part.startswith("[")
        }
    )

    return Answer(text=result["output"], sources=sources, trace=trace)
```

- [ ] **Step 6: 테스트 통과 확인**

```bash
pytest tests/workflows/test_02_2_agentic.py -v
```

Expected: 1개 PASSED

- [ ] **Step 7: 커밋**

```bash
git add workflows/02_2_langchain_agentic/ tests/workflows/test_02_2_agentic.py
git commit -m "feat: 02_2_langchain_agentic workflow — LangChain ReAct Agent with trace"
```

---

## Task 12: workflows/03_langgraph/

**Files:**
- Create: `workflows/03_langgraph/nodes/router.py`
- Create: `workflows/03_langgraph/nodes/rag.py`
- Create: `workflows/03_langgraph/nodes/direct.py`
- Create: `workflows/03_langgraph/graph/graph.py`
- Create: `workflows/03_langgraph/qa.py`
- Create: `tests/workflows/test_03_langgraph.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/workflows/test_03_langgraph.py
import importlib.util
import os
import sys
import pytest
from unittest.mock import MagicMock
from shared.models import Answer


def load_qa():
    base = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../workflows/03_langgraph")
    )
    qa_path = os.path.join(base, "qa.py")
    sys.path.insert(0, base)
    spec = importlib.util.spec_from_file_location("qa_03", qa_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.path.pop(0)
    return module


def test_run_rag_route(mocker):
    qa = load_qa()

    mock_graph = MagicMock()
    mock_graph.invoke.return_value = {
        "question": "연차 며칠이야?",
        "route": "rag",
        "answer": "연차는 15일입니다.",
        "sources": ["vacation.md"],
        "trace": [
            {"node": "router", "route": "rag"},
            {"node": "rag", "chunks_retrieved": 2},
        ],
    }
    mocker.patch.object(qa, "load_config")
    mocker.patch.object(qa, "EmbeddingService")
    mocker.patch.object(qa, "create_vector_store")
    mocker.patch.object(qa, "create_llm")
    mocker.patch.object(qa, "Retriever")
    mocker.patch.object(qa, "build_graph", return_value=mock_graph)

    answer = qa.run("연차 며칠이야?")

    assert isinstance(answer, Answer)
    assert answer.text == "연차는 15일입니다."
    assert "vacation.md" in answer.sources
    assert answer.trace[0]["node"] == "router"


def test_run_direct_route(mocker):
    qa = load_qa()

    mock_graph = MagicMock()
    mock_graph.invoke.return_value = {
        "question": "안녕하세요",
        "route": "direct",
        "answer": "안녕하세요! 무엇을 도와드릴까요?",
        "sources": [],
        "trace": [
            {"node": "router", "route": "direct"},
            {"node": "direct"},
        ],
    }
    mocker.patch.object(qa, "load_config")
    mocker.patch.object(qa, "EmbeddingService")
    mocker.patch.object(qa, "create_vector_store")
    mocker.patch.object(qa, "create_llm")
    mocker.patch.object(qa, "Retriever")
    mocker.patch.object(qa, "build_graph", return_value=mock_graph)

    answer = qa.run("안녕하세요")

    assert answer.trace[0]["route"] == "direct"
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/workflows/test_03_langgraph.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: 상태 타입 정의 — workflows/03_langgraph/nodes/router.py**

```python
from typing import TypedDict
from shared.models import SearchResult
from shared.llm.base import LLMClient

# GraphState: 그래프 전체에서 공유되는 상태
class GraphState(TypedDict):
    question: str
    route: str          # "rag" | "direct"
    context: list       # list[SearchResult] | []
    answer: str
    sources: list[str]
    trace: list[dict]


_ROUTER_PROMPT = """\
다음 질문이 회사 내부 문서(정책, 규정, 가이드라인 등)와 관련 있으면 "rag"를,
일반적인 인사나 상식 질문이면 "direct"를 한 단어로만 답하세요.

질문: {question}
분류:"""


def make_router_node(llm: LLMClient):
    def router_node(state: GraphState) -> GraphState:
        response = llm.complete(_ROUTER_PROMPT.format(question=state["question"]))
        route = "rag" if "rag" in response.lower() else "direct"
        return {
            **state,
            "route": route,
            "trace": state.get("trace", []) + [{"node": "router", "route": route}],
        }
    return router_node
```

- [ ] **Step 4: workflows/03_langgraph/nodes/rag.py 구현**

```python
from shared.retriever.retriever import Retriever
from shared.llm.base import LLMClient
from nodes.router import GraphState

_RAG_PROMPT = """\
다음 문서를 참고하여 질문에 한국어로 답하세요.

문서:
{context}

질문: {question}
답변:"""


def make_rag_node(retriever: Retriever, llm: LLMClient):
    def rag_node(state: GraphState) -> GraphState:
        results = retriever.retrieve(state["question"], top_k=5)
        context = "\n\n".join(r.chunk.text for r in results)
        sources = list({r.chunk.source for r in results})

        prompt = _RAG_PROMPT.format(context=context, question=state["question"])
        answer = llm.complete(prompt)

        return {
            **state,
            "context": results,
            "answer": answer,
            "sources": sources,
            "trace": state.get("trace", [])
            + [{"node": "rag", "chunks_retrieved": len(results)}],
        }
    return rag_node
```

- [ ] **Step 5: workflows/03_langgraph/nodes/direct.py 구현**

```python
from shared.llm.base import LLMClient
from nodes.router import GraphState

_DIRECT_PROMPT = """\
다음 질문에 친절하게 한국어로 답하세요.

질문: {question}
답변:"""


def make_direct_node(llm: LLMClient):
    def direct_node(state: GraphState) -> GraphState:
        answer = llm.complete(_DIRECT_PROMPT.format(question=state["question"]))
        return {
            **state,
            "answer": answer,
            "sources": [],
            "trace": state.get("trace", []) + [{"node": "direct"}],
        }
    return direct_node
```

- [ ] **Step 6: workflows/03_langgraph/graph/graph.py 구현**

```python
from langgraph.graph import END, StateGraph
from nodes.router import GraphState, make_router_node
from nodes.rag import make_rag_node
from nodes.direct import make_direct_node


def build_graph(llm, retriever):
    graph = StateGraph(GraphState)

    graph.add_node("router", make_router_node(llm))
    graph.add_node("rag", make_rag_node(retriever, llm))
    graph.add_node("direct", make_direct_node(llm))

    graph.set_entry_point("router")
    graph.add_conditional_edges(
        "router",
        lambda state: state["route"],
        {"rag": "rag", "direct": "direct"},
    )
    graph.add_edge("rag", END)
    graph.add_edge("direct", END)

    return graph.compile()
```

- [ ] **Step 7: workflows/03_langgraph/qa.py 구현**

```python
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from graph.graph import build_graph
from shared.config import load_config
from shared.llm.factory import create_llm
from shared.models import Answer
from shared.retriever.embedding import EmbeddingService
from shared.retriever.retriever import Retriever
from shared.vector_store.factory import create_vector_store


def run(question: str) -> Answer:
    config = load_config()
    embedder = EmbeddingService(config.embedding_model)
    store = create_vector_store(config)
    llm = create_llm(config)
    retriever = Retriever(store, embedder)

    graph = build_graph(llm, retriever)
    state = graph.invoke(
        {
            "question": question,
            "route": "",
            "context": [],
            "answer": "",
            "sources": [],
            "trace": [],
        }
    )

    return Answer(
        text=state["answer"],
        sources=state["sources"],
        trace=state["trace"],
    )
```

- [ ] **Step 8: 테스트 통과 확인**

```bash
pytest tests/workflows/test_03_langgraph.py -v
```

Expected: 2개 PASSED

- [ ] **Step 9: 커밋**

```bash
git add workflows/03_langgraph/ tests/workflows/test_03_langgraph.py
git commit -m "feat: 03_langgraph workflow — StateGraph routing with extensible nodes"
```

---

## Task 13: evals/ — 비교 평가셋

**Files:**
- Create: `evals/questions.yaml`
- Create: `evals/runner.py`

- [ ] **Step 1: evals/questions.yaml 작성**

```yaml
questions:
  - question: "연차는 며칠이야?"
    expected_keywords: ["연차", "일"]
    expected_source: "vacation-policy.md"
  - question: "코드 리뷰할 때 주의사항이 뭐야?"
    expected_keywords: ["리뷰", "PR"]
    expected_source: "code-review-guide.md"
  - question: "팀 구조가 어떻게 돼?"
    expected_keywords: ["팀", "구조"]
    expected_source: "team-structure.md"
  - question: "보안 정책에서 비밀번호 규정이 뭐야?"
    expected_keywords: ["비밀번호", "보안"]
    expected_source: "security-policy.md"
  - question: "온보딩 절차가 어떻게 돼?"
    expected_keywords: ["온보딩", "입사"]
    expected_source: "onboarding.md"
```

- [ ] **Step 2: evals/runner.py 구현**

```python
import importlib.util
import os
import sys
import time
from typing import Any

import yaml

from shared.models import Answer

_WORKFLOW_PATHS = {
    "simple": "workflows/01_simple/qa.py",
    "langchain": "workflows/02_1_langchain_basic/qa.py",
    "agentic": "workflows/02_2_langchain_agentic/qa.py",
    "langgraph": "workflows/03_langgraph/qa.py",
}

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_workflow(mode: str):
    qa_path = os.path.join(_ROOT, _WORKFLOW_PATHS[mode])
    workflow_dir = os.path.dirname(qa_path)
    sys.path.insert(0, workflow_dir)
    spec = importlib.util.spec_from_file_location(f"qa_{mode}", qa_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.path.pop(0)
    return module


def run_all(question: str) -> dict[str, dict[str, Any]]:
    results = {}
    for mode in _WORKFLOW_PATHS:
        module = _load_workflow(mode)
        start = time.time()
        answer: Answer = module.run(question)
        elapsed = time.time() - start
        results[mode] = {"answer": answer, "elapsed_sec": round(elapsed, 2)}
    return results


def print_comparison(question: str, results: dict[str, dict[str, Any]]) -> None:
    sep = "=" * 70
    print(f"\n{sep}")
    print(f"질문: {question}")
    print(f"{sep}\n")
    for mode, data in results.items():
        answer: Answer = data["answer"]
        print(f"[{mode.upper()}]  ({data['elapsed_sec']}s)")
        print(f"  답변: {answer.text}")
        print(f"  출처: {', '.join(answer.sources) or '없음'}")
        if answer.trace:
            print(f"  trace ({len(answer.trace)}단계):")
            for step in answer.trace:
                print(f"    {step}")
        print()


def load_questions(yaml_path: str | None = None) -> list[dict]:
    path = yaml_path or os.path.join(os.path.dirname(__file__), "questions.yaml")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)["questions"]
```

- [ ] **Step 3: 커밋**

```bash
git add evals/
git commit -m "feat: evals — question set and multi-mode comparison runner"
```

---

## Task 14: main.py — 단일 CLI 진입점

**Files:**
- Create: `main.py`

- [ ] **Step 1: main.py 구현**

```python
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
```

- [ ] **Step 2: .env 파일 생성 (실제 API 키 입력)**

```bash
cp .env.example .env
# .env 파일에 실제 OPENAI_API_KEY 또는 ANTHROPIC_API_KEY 입력
```

- [ ] **Step 3: 인덱스 빌드 확인**

```bash
python main.py --build-index
```

Expected: `인덱싱 완료: N개 청크 (.../docs)`

- [ ] **Step 4: 01_simple 동작 확인**

```bash
python main.py --mode simple -q "연차는 며칠이야?"
```

Expected: 답변 텍스트 + 출처 출력, trace 없음

- [ ] **Step 5: 전체 테스트 통과 확인**

```bash
pytest tests/ -v --ignore=tests/workflows
```

Expected: 전체 PASSED (워크플로우 통합 테스트는 실제 API 키 필요)

- [ ] **Step 6: 최종 커밋**

```bash
git add main.py .env.example
git commit -m "feat: main.py — single CLI entrypoint with --mode and --build-index"
```

---

## 검증 체크리스트

```bash
# shared 단위 테스트
pytest tests/shared/ -v

# --mode all 비교 실행 (실제 API 키 필요)
python main.py --mode all -q "연차는 며칠이야?"
python main.py --mode all -q "코드 리뷰할 때 주의사항이 뭐야?"

# 각 워크플로우 개별 실행
python main.py --mode simple -q "팀 구조가 어떻게 돼?"
python main.py --mode langchain -q "보안 정책에서 비밀번호 규정이 뭐야?"
python main.py --mode agentic -q "온보딩 절차가 어떻게 돼?"
python main.py --mode langgraph -q "재택근무 정책이 뭐야?"
```
