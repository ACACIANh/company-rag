# RAG 아키텍처 개선 설계

- **작성일**: 2026-05-21
- **출처**: PRD.md의 6가지 비판점 (Retriever/VectorStore 경계, Chunker 누락, Reranker 누락, Orchestrator 비대화, Embedder Adapter 부재, Observability 부재)
- **목표**: PRD #1안(책임 분리 강화) 구조로 전환하되, 기존 4개 데모 workflow는 보존

## 1. 범위 및 결정 사항

| 항목 | 결정 |
|---|---|
| 다룰 비판점 | PRD #1~#6 전부 |
| 기존 workflow(01~03) | deprecated로 보존. 테스트는 그대로 통과해야 함 |
| 새 workflow | `workflows/04_pipeline/`에 1개 추가 |
| Reranker 구현체 | `Reranker` ABC + `NoOpReranker`만. BGE/Cohere는 후속 |
| Observability 범위 | Tracing + Cache + Eval 전부 |
| Step 추상화 | `Step(ABC).run(ctx) -> ctx` + `Pipeline([steps]).run()` |

## 2. 아키텍처

### 디렉터리 구조

```
shared/
├── models.py                     # Chunk/SearchResult/Answer + Document(신규), Chunk.metadata 추가
├── config.py                     # 변경 없음
├── loader/                       # 신규
│   ├── base.py                   # DocumentLoader ABC
│   └── markdown_loader.py
├── chunker/                      # 신규
│   ├── base.py                   # Chunker ABC
│   └── fixed_size_chunker.py     # 현 Indexer._chunk_text 이식
├── embedder/                     # retriever/embedding.py 이동 + Adapter 정렬
│   ├── base.py                   # Embedder ABC
│   ├── sentence_transformer_embedder.py
│   └── adapters/
│       └── langchain_adapter.py
├── vector_store/                 # 변경 없음
├── retriever/
│   ├── base.py                   # Retriever ABC (검색 전략 자리)
│   └── basic_retriever.py        # 현 Retriever 이식 (벡터 검색만)
├── reranker/                     # 신규
│   ├── base.py                   # Reranker ABC
│   └── noop_reranker.py
├── indexer/
│   └── indexer.py                # Loader+Chunker+Embedder+Store 조합만
├── orchestrator/                 # 신규
│   ├── context.py                # Context dataclass
│   ├── step.py                   # Step ABC
│   └── pipeline.py               # Pipeline
└── observability/                # 신규
    ├── tracer.py                 # Tracer, Span
    ├── cache.py                  # LRUCache, CachedEmbedder, CachedLLM
    └── eval/
        ├── metrics.py            # recall_at_k, faithfulness, latency_ms
        └── evaluator.py          # Evaluator

workflows/
├── 01_simple/                    # deprecated, 유지
├── 02_1_langchain_basic/         # deprecated, 유지
├── 02_2_langchain_agentic/       # deprecated, 유지
├── 03_langgraph/                 # deprecated, 유지
└── 04_pipeline/                  # 신규
    ├── qa.py                     # run(question) -> Answer
    ├── steps.py                  # RetrieveStep, RerankStep, GenerateStep
    └── prompts.py
```

### PRD 비판점 → 해결 매핑

| PRD 비판점 | 해결 방식 |
|---|---|
| #1 Retriever ↔ VectorStore 경계 모호 | `Retriever` ABC를 두고 "검색 전략" 자리를 명시. 1차 구현은 `BasicRetriever`(벡터 검색). 하이브리드/MMR은 같은 인터페이스의 다른 구현체로 추가하면 됨. |
| #2 Chunker 누락 | Loader → Chunker → Embedder → VectorStore 4단계 분리. Indexer는 조합만. |
| #3 Reranker 누락 | `Reranker` ABC + `NoOpReranker`. Pipeline에서 Step으로 명시 노출. |
| #4 Orchestrator 비대화 | `Step + Pipeline + Context`. 새 workflow는 Step 조합으로 작성. multi-hop은 Step 추가로 확장 가능. |
| #5 Embedder Adapter 부재 | `shared/embedder/`로 승격, `adapters/` 동위 배치. |
| #6 Observability 부재 | `shared/observability/` 횡단 관심사. Tracer는 Pipeline이 자동 부착, Cache는 데코레이터, Eval은 별도 metric/Evaluator. |

## 3. 컴포넌트 인터페이스

### models.py

```python
@dataclass
class Document:
    text: str
    source: str
    metadata: dict = field(default_factory=dict)

@dataclass
class Chunk:
    text: str
    source: str
    chunk_id: str
    metadata: dict = field(default_factory=dict)   # 신규 필드
```

`SearchResult`, `Answer`는 현재 그대로.

### 핵심 ABC

```python
class DocumentLoader(ABC):
    @abstractmethod
    def load(self, path: str) -> list[Document]: ...

class Chunker(ABC):
    @abstractmethod
    def chunk(self, doc: Document) -> list[Chunk]: ...

class Embedder(ABC):
    @abstractmethod
    def embed(self, text: str) -> list[float]: ...
    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...

class Retriever(ABC):
    @abstractmethod
    def retrieve(self, query: str, top_k: int = 5) -> list[SearchResult]: ...

class Reranker(ABC):
    @abstractmethod
    def rerank(
        self, query: str, results: list[SearchResult], top_k: int | None = None
    ) -> list[SearchResult]: ...
```

### 1차 구현체

- `MarkdownLoader`: 디렉터리에서 `.md` 읽어 Document 리스트
- `FixedSizeChunker(chunk_size, chunk_overlap)`: 현 `Indexer._chunk_text` 이식
- `SentenceTransformerEmbedder(model_name)`: 현 `EmbeddingService` 이식
- `BasicRetriever(embedder, store)`: 현 `Retriever` 이식
- `NoOpReranker`: `results[:top_k]` 그대로 반환

### Indexer (슬림화)

```python
class Indexer:
    def __init__(
        self,
        loader: DocumentLoader,
        chunker: Chunker,
        embedder: Embedder,
        store: VectorStore,
    ): ...

    def index(self, path: str) -> int:
        docs = self._loader.load(path)
        chunks = [c for d in docs for c in self._chunker.chunk(d)]
        if not chunks:
            return 0
        embeddings = self._embedder.embed_batch([c.text for c in chunks])
        self._store.add(chunks, embeddings)
        return len(chunks)
```

### Orchestrator

```python
@dataclass
class Context:
    query: str
    chunks: list[SearchResult] = field(default_factory=list)
    answer_text: str | None = None
    metadata: dict = field(default_factory=dict)

class Step(ABC):
    name: str
    @abstractmethod
    def run(self, ctx: Context) -> Context: ...

class Pipeline:
    def __init__(self, steps: list[Step], tracer: Tracer | None = None): ...
    def run(self, ctx: Context) -> Context:
        for step in self._steps:
            if self._tracer:
                with self._tracer.span(step.name) as span:
                    try:
                        ctx = step.run(ctx)
                    except Exception as e:
                        span.metadata["status"] = "error"
                        span.metadata["error"] = type(e).__name__
                        raise
            else:
                ctx = step.run(ctx)
        return ctx
```

### Step 구현체 (workflows/04_pipeline/steps.py)

- `RetrieveStep(retriever, top_k=10)` → `ctx.chunks`
- `RerankStep(reranker, top_k=5)` → `ctx.chunks` (over-fetch 후 reranker로 좁힘)
- `GenerateStep(llm, prompt_template)` → `ctx.answer_text`

Step은 shared가 아닌 workflow 소유. PRD의 "프롬프트는 워크플로우 소유" 원칙과 일관.

### Observability

```python
# tracer.py
@dataclass
class Span:
    name: str
    started_at: float
    ended_at: float
    metadata: dict

class Tracer:
    def __init__(self): self.spans: list[Span] = []
    @contextmanager
    def span(self, name: str, **meta): ...
    def dump(self) -> list[dict]: ...

# cache.py
class LRUCache:
    def __init__(self, max_size: int = 1024): ...
    def get(self, key: str) -> Any | None: ...
    def set(self, key: str, value: Any) -> None: ...

class CachedEmbedder(Embedder):  # 데코레이터
    def __init__(self, inner: Embedder, cache: LRUCache): ...

class CachedLLM(LLM):  # 데코레이터
    def __init__(self, inner: LLM, cache: LRUCache): ...

# eval/metrics.py
def recall_at_k(retrieved_sources: list[str], expected_source: str, k: int) -> float: ...
def latency_ms(span: Span) -> float: ...
def faithfulness(answer: str, context: str, judge_llm: LLM) -> float: ...  # LLM judge

# eval/evaluator.py
@dataclass
class EvalCase:
    question: str
    expected_keywords: list[str]
    expected_source: str

@dataclass
class EvalReport:
    cases: list[dict]
    aggregate: dict

class Evaluator:
    def __init__(self, metrics: list[Callable]): ...
    def evaluate(
        self, workflow: Callable[[str], Answer], cases: list[EvalCase]
    ) -> EvalReport: ...
```

## 4. 데이터 흐름

### Indexing

```
docs/*.md
   │
   ▼ MarkdownLoader.load()
list[Document]
   │
   ▼ FixedSizeChunker.chunk() (각 Document)
list[Chunk]
   │
   ▼ CachedEmbedder.embed_batch()
list[list[float]]
   │
   ▼ VectorStore.add(chunks, embeddings)
```

### Query

```
question (str)
   │
   ▼ Context(query=question)
Pipeline.run(ctx) — Tracer가 각 Step을 span으로 감쌈
   │
   ├── RetrieveStep    → BasicRetriever.retrieve(q, top_k=10) → ctx.chunks
   ├── RerankStep      → NoOpReranker.rerank(q, ctx.chunks, top_k=5) → ctx.chunks
   └── GenerateStep    → CachedLLM.complete(prompt) → ctx.answer_text
   │
   ▼
Answer(text=ctx.answer_text,
       sources=unique(c.chunk.source for c in ctx.chunks),
       trace=tracer.dump())
```

### Tracer 부착 지점

- Pipeline.run이 각 Step을 span으로 자동 감쌈.
- Step 내부에서 추가 span은 만들지 않음 (1차).
- `tracer.dump()`은 `Answer.trace`로 들어가 main.py가 그대로 출력.

### Cache 부착 지점

- **Embedder 데코레이터**: 키 = SHA256(text). Indexing/Query에서 같은 인스턴스 공유 가능.
- **LLM 데코레이터**: 키 = SHA256(prompt + model_name).
- TTL 없음. 프로세스 수명 동안만 유지.

### Eval

```
questions.yaml → list[EvalCase] → Evaluator(metrics).evaluate(workflow, cases) → EvalReport → print
```

기존 `run_all` 비교 출력은 유지하되 Evaluator를 내부적으로 사용.

### main.py 사용 패턴

```python
def _build_index():
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
    count = indexer.index("./docs")
    print(f"인덱싱 완료: {count}개 청크")
```

## 5. 에러 처리

### 원칙

- 내부 컴포넌트끼리는 신뢰. 방어 코드 안 쌓음.
- 시스템 경계(파일, 외부 API, 사용자 입력)에서만 검증.
- fail-fast. 무음 fallback 금지.

### 컴포넌트별 방침

| 컴포넌트 | 에러 종류 | 처리 |
|---|---|---|
| `MarkdownLoader` | 경로 미존재 | `FileNotFoundError` 전파 |
| `MarkdownLoader` | `.md` 0개 | 빈 리스트 |
| `FixedSizeChunker` | 빈 문서 | 빈 리스트 |
| `Embedder` | 모델 로드 실패 | 라이브러리 예외 전파 |
| `VectorStore` | 컬렉션 없음 | 어댑터별 자체 처리, 첫 add에서 자동 생성 |
| `Retriever` | 결과 0개 | 빈 리스트 |
| `Reranker` | 입력 0개 | 빈 리스트 |
| `LLM` | API 실패 | 예외 전파, 재시도 없음 |
| `Pipeline` | Step 중간 실패 | Tracer가 span에 `status=error` 기록 후 re-raise |
| `Cache` | 미스 | inner 호출 후 저장. 실패 시 저장 안 함 |
| `Evaluator` | 한 케이스 실패 | 해당 케이스만 `error=...`로 기록, 나머지 진행 |

### Config

`os.getenv(..., default)`로 기본값. API 키만 비어있을 수 있고, 외부 클라이언트 첫 호출에서 자체 에러.

### 의도적 누락 (후속 작업)

- 재시도/백오프
- 타임아웃
- Circuit breaker
- 외부 모니터링 연동(Sentry 등)
- Pydantic 검증

## 6. 테스트 전략

### 원칙

- 인터페이스마다 fake/stub.
- 기존 테스트(deprecated workflow 4개 + 그들이 쓰는 컴포넌트) 무손상.
- 신규 컴포넌트는 TDD로 작성.

### 신규 테스트 (`tests/shared/`)

| 파일 | 대상 | 핵심 케이스 |
|---|---|---|
| `test_loader.py` | `MarkdownLoader` | 디렉터리 → Document 리스트, 빈 디렉터리, `.md` 아닌 파일 무시 |
| `test_chunker.py` | `FixedSizeChunker` | 분할 정확성, overlap, 빈 문서, 짧은 문서 |
| `test_embedder.py` | `SentenceTransformerEmbedder` | embed/embed_batch shape, ABC 계약 |
| `test_embedder_cache.py` | `CachedEmbedder` | 캐시 히트 시 inner 미호출, batch 부분 캐시, LRU eviction |
| `test_retriever.py` (수정) | `BasicRetriever` | ABC 계약 추가, 빈 store |
| `test_reranker.py` | `NoOpReranker` | 순서 유지, top_k 자르기, 빈 입력 |
| `test_orchestrator.py` | `Pipeline + Step` | 순차 실행, Tracer 부착, 예외 시 span `error` 후 re-raise, Context 누적 |
| `test_tracer.py` | `Tracer/Span` | 시작/종료 시간, dump 형식 |
| `test_cache.py` | `LRUCache` | get/set, eviction, 덮어쓰기 |
| `test_llm_cache.py` | `CachedLLM` | 동일 prompt 1회 호출, 다른 prompt 매번 |
| `test_indexer.py` (수정) | 새 `Indexer` | 의존성 4개 mock, 빈 docs 시 store 미호출 |
| `test_eval.py` | metrics, Evaluator | `recall_at_k`, `latency_ms`, 일부 케이스 실패 시 나머지 진행 |

### 신규 테스트 (`tests/workflows/`)

| 파일 | 대상 | 핵심 케이스 |
|---|---|---|
| `test_04_pipeline.py` | `workflows/04_pipeline/qa.py` | end-to-end with mocks, trace 3 span, source 중복 제거 |

### Fake 패턴

`tests/shared/fakes.py` 신규: `FakeEmbedder`, `FakeVectorStore`, `FakeLLM`, `FakeReranker`. 외부 의존성 없이 빠른 단위 테스트 가능.

### 기존 테스트

- `test_indexer.py`: 새 시그니처에 맞춰 수정
- `test_retriever.py`: 인터페이스화 반영해 약간 손봄
- 나머지 (`test_adapters.py`, `test_llm.py`, `test_vector_store.py`, `test_models.py`, `test_config.py`, `tests/workflows/test_0*.py`): 무손상

### Eval ≠ 테스트

- 테스트: 코드가 시그니처대로 동작하는가 (pytest)
- Eval: RAG 정답 품질 (Evaluator, 별도 실행)
- pytest 안에서 Eval 자동 실행 안 함

## 7. 마이그레이션 순서 (구현 단계에서 참조)

1. `shared/models.py`에 Document, Chunk.metadata 추가
2. `shared/observability/`(tracer, cache, eval) 먼저 — 의존성 없음, 가장 안쪽
3. `shared/loader/`, `shared/chunker/`, `shared/embedder/` — 1차 구현체 + 테스트
4. `shared/retriever/`, `shared/reranker/` — 인터페이스화 + 1차 구현체
5. **기존 deprecated workflow의 import 경로 업데이트**: `shared.retriever.embedding.EmbeddingService` → `shared.embedder.SentenceTransformerEmbedder`, `shared.retriever.retriever.Retriever` → `shared.retriever.BasicRetriever`. shim/alias 없이 직접 교체. 기존 workflow는 보존하되 새 경로를 쓰도록 한다.
6. `shared/indexer/` — 새 시그니처로 교체. `test_indexer.py` 수정. main.py의 `_build_index`도 같이 업데이트(loader/chunker/embedder/store 주입)
7. `shared/orchestrator/` — Step/Pipeline/Context
8. `workflows/04_pipeline/` — Step 구현체 + qa.py + 프롬프트
9. `main.py` — 새 mode `"pipeline"` 등록 (`--mode pipeline`)
10. `evals/runner.py` — Evaluator 사용으로 리팩토링, questions.yaml 그대로
11. 기존 deprecated workflow 동작 확인 (smoke run + `tests/workflows/test_0*.py` 통과)

각 단계는 통과해야 다음으로. 중간 커밋 가능.

### 5단계 import 매핑 (정확한 치환)

| 기존 | 새 |
|---|---|
| `from shared.retriever.embedding import EmbeddingService` | `from shared.embedder import SentenceTransformerEmbedder` |
| `EmbeddingService(model_name)` | `SentenceTransformerEmbedder(model_name)` |
| `from shared.retriever.retriever import Retriever` | `from shared.retriever import BasicRetriever` |
| `Retriever(store, embedder)` | `BasicRetriever(store, embedder)` |

영향 받는 파일:
- `main.py`
- `workflows/01_simple/qa.py`
- `workflows/02_1_langchain_basic/qa.py`, `workflows/02_1_langchain_basic/chain/chain.py`
- `workflows/02_2_langchain_agentic/qa.py`, `workflows/02_2_langchain_agentic/tools/rag_tool.py`
- `workflows/03_langgraph/qa.py`, `workflows/03_langgraph/nodes/*`
- `tests/shared/test_retriever.py`, `tests/shared/test_indexer.py`

(실제 import 위치는 구현 시 grep으로 재확인.)

## 8. 안 하는 것 (1차 범위 밖)

- BGE/Cohere Reranker 구현체
- LLM 재시도/타임아웃/Circuit breaker
- 외부 트레이서 연동 (LangSmith, Langfuse, OTel)
- 캐시 영속화/TTL
- Pydantic 검증
- 청킹 전략 추가 (semantic, recursive 등)
- 하이브리드 검색, MMR, 메타필터
- multi-hop, conversational RAG workflow
