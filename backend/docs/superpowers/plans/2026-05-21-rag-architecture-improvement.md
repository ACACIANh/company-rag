# RAG Architecture Improvement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** PRD.md의 6가지 비판점을 해결하기 위해 RAG 아키텍처를 책임 분리 강화 구조로 전환하고 새 `workflows/pipeline/`를 추가한다. (디렉터리 이름은 `pipeline` — Python identifier 규칙상 숫자 prefix `04_`는 일반 import path로 사용 불가하여 spec의 `04_pipeline` 표기 대신 채택.)

**Architecture:** 기존 1~3번 워크플로우는 코드 전체 주석 처리로 보존. `shared/` 아래 `loader, chunker, embedder, retriever, reranker, indexer, orchestrator, observability` 컴포넌트를 ABC + 구현체로 분리. `Step + Pipeline + Context` 추상화 위에서 새 워크플로우를 조립한다.

**Tech Stack:** Python 3.10+, sentence-transformers, chromadb, openai/anthropic SDK, pytest, pyyaml. (요구사항 무변경.)

**Spec:** `docs/superpowers/specs/2026-05-21-rag-architecture-improvement-design.md`

---

## Task 1: Deprecated workflow 코드 주석 처리

**Files:**
- Modify: `workflows/01_simple/qa.py`, `workflows/02_1_langchain_basic/qa.py`, `workflows/02_1_langchain_basic/chain/chain.py`, `workflows/02_2_langchain_agentic/qa.py`, `workflows/02_2_langchain_agentic/tools/rag_tool.py`, `workflows/02_2_langchain_agentic/agent/*.py`, `workflows/03_langgraph/qa.py`, `workflows/03_langgraph/graph/*.py`, `workflows/03_langgraph/nodes/*.py`
- Modify: `tests/workflows/test_01_simple.py`, `tests/workflows/test_02_1_langchain.py`, `tests/workflows/test_02_2_agentic.py`, `tests/workflows/test_03_langgraph.py`
- Modify: `main.py`, `evals/runner.py`

- [ ] **Step 1: 영향 받는 파일 전수 조사**

Run: `find workflows/0[1-3]* -name '*.py' -not -name '__init__.py' | sort`
Expected: `01_simple/qa.py`, `02_1_langchain_basic/chain/chain.py`, `02_1_langchain_basic/qa.py`, `02_2_langchain_agentic/agent/*.py`, `02_2_langchain_agentic/qa.py`, `02_2_langchain_agentic/tools/rag_tool.py`, `03_langgraph/graph/*.py`, `03_langgraph/nodes/*.py`, `03_langgraph/qa.py`

또한 `find tests/workflows -name 'test_0*.py'` 결과를 확보.

- [ ] **Step 2: 각 deprecated workflow .py 파일을 주석 처리**

각 파일에 대해:
1. 첫 줄에 `# DEPRECATED: 새 구조(workflows/pipeline/)로 대체됨. 학습 참조용으로 코드 형태만 보존.` 삽입
2. 그 아래 모든 코드/import/공백이 아닌 라인 앞에 `# ` 추가
3. 빈 줄은 유지
4. `__init__.py`는 그대로(빈 모듈)

**효율적 명령** (각 파일에 적용):
```bash
python3 - <<'PY'
import sys, pathlib
files = [
    "workflows/01_simple/qa.py",
    "workflows/02_1_langchain_basic/qa.py",
    "workflows/02_1_langchain_basic/chain/chain.py",
    "workflows/02_2_langchain_agentic/qa.py",
    "workflows/02_2_langchain_agentic/tools/rag_tool.py",
    "workflows/03_langgraph/qa.py",
]
# agent/ nodes/ graph/ 디렉터리도 추가
import glob
files += [
    f for d in ("workflows/02_2_langchain_agentic/agent",
                "workflows/03_langgraph/graph",
                "workflows/03_langgraph/nodes")
    for f in glob.glob(d + "/*.py") if not f.endswith("__init__.py")
]
header = "# DEPRECATED: 새 구조(workflows/pipeline/)로 대체됨. 학습 참조용으로 코드 형태만 보존.\n"
for p in files:
    text = pathlib.Path(p).read_text(encoding="utf-8")
    new = header + "".join(
        line if line.strip() == "" else "# " + line
        for line in text.splitlines(keepends=True)
    )
    pathlib.Path(p).write_text(new, encoding="utf-8")
    print(f"commented out: {p}")
PY
```

- [ ] **Step 3: 테스트 파일도 동일하게 주석 처리**

```bash
python3 - <<'PY'
import pathlib, glob
header = "# DEPRECATED: 대응 workflow가 주석 처리되어 비활성화됨.\n"
for p in glob.glob("tests/workflows/test_0*.py"):
    text = pathlib.Path(p).read_text(encoding="utf-8")
    new = header + "".join(
        line if line.strip() == "" else "# " + line
        for line in text.splitlines(keepends=True)
    )
    pathlib.Path(p).write_text(new, encoding="utf-8")
    print(f"commented out: {p}")
PY
```

- [ ] **Step 4: main.py에서 deprecated mode 제거**

`main.py`의 `_WORKFLOW_PATHS`를 `{}`로 비우고, `--mode` argparse choices에서 `"simple", "langchain", "agentic", "langgraph"`를 모두 제거(현 시점엔 `all`만 임시로 유지하거나 같이 제거 — 다음 Task에서 `pipeline` 추가 예정).

수정 후 `main.py`의 관련 부분:
```python
_WORKFLOW_PATHS = {}  # 새 mode는 Task 14에서 등록
...
parser.add_argument(
    "--mode",
    choices=[],  # Task 14에서 "pipeline" 추가
    help="실행할 워크플로우",
)
```

argparse가 빈 choices를 싫어할 수 있으니, 임시로:
```python
parser.add_argument("--mode", help="실행할 워크플로우 (Task 14 이후 'pipeline')")
```

- [ ] **Step 5: evals/runner.py의 _WORKFLOW_PATHS도 비움**

`_WORKFLOW_PATHS = {}` 로 변경. 나머지 함수는 Task 15에서 리팩토링.

- [ ] **Step 6: pytest 실행 — 주석 처리된 테스트가 모두 collect 안 되거나 통과해야 함**

Run: `pytest -q`
Expected: 기존 deprecated workflow 테스트는 0 tests collected from those files. 다른 테스트(`tests/shared/test_*`)는 그대로 통과해야 함. **`test_indexer.py`, `test_retriever.py`는 이 시점에는 아직 깨지지 않음** (`shared/indexer/indexer.py`, `shared/retriever/retriever.py`가 그대로 있음).

- [ ] **Step 7: 커밋**

```bash
git add workflows/ tests/workflows/ main.py evals/runner.py
git commit -m "chore: comment out deprecated workflows 01-03 for new architecture"
```

---

## Task 2: shared/models.py에 Document 추가, Chunk.metadata 필드 추가

**Files:**
- Modify: `shared/models.py`
- Modify: `tests/shared/test_models.py`

- [ ] **Step 1: test_models.py에 실패 테스트 추가**

`tests/shared/test_models.py` 끝에:
```python
def test_document_dataclass():
    from shared.models import Document
    d = Document(text="hello", source="a.md")
    assert d.text == "hello"
    assert d.source == "a.md"
    assert d.metadata == {}

def test_document_with_metadata():
    from shared.models import Document
    d = Document(text="t", source="s", metadata={"page": 1})
    assert d.metadata == {"page": 1}

def test_chunk_has_metadata_default_empty():
    from shared.models import Chunk
    c = Chunk(text="t", source="s", chunk_id="id1")
    assert c.metadata == {}

def test_chunk_with_metadata():
    from shared.models import Chunk
    c = Chunk(text="t", source="s", chunk_id="id1", metadata={"k": "v"})
    assert c.metadata == {"k": "v"}
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/shared/test_models.py -v`
Expected: 새 4개 테스트 FAIL (`Document` 미존재, `Chunk.metadata` 미존재).

- [ ] **Step 3: shared/models.py 업데이트**

```python
from dataclasses import dataclass, field


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
    metadata: dict = field(default_factory=dict)


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

Run: `pytest tests/shared/test_models.py -v`
Expected: 모든 테스트 PASS.

- [ ] **Step 5: 커밋**

```bash
git add shared/models.py tests/shared/test_models.py
git commit -m "feat(models): add Document, add metadata field to Chunk"
```

---

## Task 3: shared/observability/tracer.py

**Files:**
- Create: `shared/observability/__init__.py`
- Create: `shared/observability/tracer.py`
- Create: `tests/shared/test_tracer.py`

- [ ] **Step 1: tests/shared/test_tracer.py 작성 (실패 테스트)**

```python
import time
import pytest
from shared.observability.tracer import Tracer, Span


def test_tracer_records_single_span():
    tracer = Tracer()
    with tracer.span("step1") as s:
        s.metadata["k"] = "v"
    assert len(tracer.spans) == 1
    span = tracer.spans[0]
    assert span.name == "step1"
    assert span.metadata == {"k": "v"}
    assert span.ended_at >= span.started_at


def test_tracer_records_multiple_spans_in_order():
    tracer = Tracer()
    with tracer.span("a"):
        pass
    with tracer.span("b"):
        pass
    assert [s.name for s in tracer.spans] == ["a", "b"]


def test_tracer_records_span_on_exception():
    tracer = Tracer()
    with pytest.raises(ValueError):
        with tracer.span("explode") as s:
            s.metadata["status"] = "error"
            raise ValueError("boom")
    assert len(tracer.spans) == 1
    assert tracer.spans[0].metadata.get("status") == "error"


def test_tracer_dump_returns_list_of_dicts():
    tracer = Tracer()
    with tracer.span("step1") as s:
        s.metadata["latency_ms"] = 42
    dumped = tracer.dump()
    assert isinstance(dumped, list)
    assert isinstance(dumped[0], dict)
    assert dumped[0]["name"] == "step1"
    assert "started_at" in dumped[0]
    assert "ended_at" in dumped[0]
    assert dumped[0]["metadata"] == {"latency_ms": 42}
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/shared/test_tracer.py -v`
Expected: ImportError / ModuleNotFoundError.

- [ ] **Step 3: shared/observability/__init__.py 생성**

빈 파일.

- [ ] **Step 4: shared/observability/tracer.py 작성**

```python
import time
from contextlib import contextmanager
from dataclasses import dataclass, field


@dataclass
class Span:
    name: str
    started_at: float
    ended_at: float = 0.0
    metadata: dict = field(default_factory=dict)


class Tracer:
    def __init__(self) -> None:
        self.spans: list[Span] = []

    @contextmanager
    def span(self, name: str):
        s = Span(name=name, started_at=time.time())
        self.spans.append(s)
        try:
            yield s
        finally:
            s.ended_at = time.time()

    def dump(self) -> list[dict]:
        return [
            {
                "name": s.name,
                "started_at": s.started_at,
                "ended_at": s.ended_at,
                "metadata": dict(s.metadata),
            }
            for s in self.spans
        ]
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `pytest tests/shared/test_tracer.py -v`
Expected: 4 PASSED.

- [ ] **Step 6: 커밋**

```bash
git add shared/observability/ tests/shared/test_tracer.py
git commit -m "feat(observability): add Tracer with span contextmanager"
```

---

## Task 4: shared/observability/cache.py — LRUCache + CachedEmbedder + CachedLLM

**Files:**
- Create: `shared/observability/cache.py`
- Create: `tests/shared/test_cache.py`
- Create: `tests/shared/test_embedder_cache.py`
- Create: `tests/shared/test_llm_cache.py`

`CachedEmbedder`와 `CachedLLM`은 아직 정의되지 않은 ABC(`Embedder`, `LLMClient`)에 의존하지만, `LLMClient`는 이미 `shared/llm/base.py`에 있음. `Embedder` ABC는 Task 8에서 정의되므로, 이 Task에서는 `CachedEmbedder`를 **duck-typed wrapper**로 작성하고 Task 8에서 ABC를 import해 형식을 정합한다.

- [ ] **Step 1: tests/shared/test_cache.py 작성 (LRU 단독)**

```python
from shared.observability.cache import LRUCache


def test_lru_set_get():
    c = LRUCache(max_size=3)
    c.set("a", 1)
    assert c.get("a") == 1


def test_lru_miss_returns_none():
    c = LRUCache(max_size=3)
    assert c.get("missing") is None


def test_lru_eviction_oldest_first():
    c = LRUCache(max_size=2)
    c.set("a", 1)
    c.set("b", 2)
    c.set("c", 3)  # evicts "a"
    assert c.get("a") is None
    assert c.get("b") == 2
    assert c.get("c") == 3


def test_lru_get_promotes_recency():
    c = LRUCache(max_size=2)
    c.set("a", 1)
    c.set("b", 2)
    _ = c.get("a")   # "a" is now most-recent
    c.set("c", 3)    # evicts "b"
    assert c.get("a") == 1
    assert c.get("b") is None
    assert c.get("c") == 3


def test_lru_overwrite():
    c = LRUCache(max_size=2)
    c.set("a", 1)
    c.set("a", 2)
    assert c.get("a") == 2
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/shared/test_cache.py -v`
Expected: ImportError.

- [ ] **Step 3: LRUCache 구현**

`shared/observability/cache.py`:
```python
import hashlib
from collections import OrderedDict
from typing import Any


class LRUCache:
    def __init__(self, max_size: int = 1024) -> None:
        self._max = max_size
        self._data: OrderedDict[str, Any] = OrderedDict()

    def get(self, key: str) -> Any | None:
        if key not in self._data:
            return None
        self._data.move_to_end(key)
        return self._data[key]

    def set(self, key: str, value: Any) -> None:
        if key in self._data:
            self._data.move_to_end(key)
        self._data[key] = value
        while len(self._data) > self._max:
            self._data.popitem(last=False)
```

- [ ] **Step 4: LRU 테스트 통과 확인**

Run: `pytest tests/shared/test_cache.py -v`
Expected: 5 PASSED.

- [ ] **Step 5: tests/shared/test_embedder_cache.py 작성**

```python
from unittest.mock import MagicMock
from shared.observability.cache import LRUCache, CachedEmbedder


def test_cached_embedder_calls_inner_on_miss():
    inner = MagicMock()
    inner.embed.return_value = [0.1, 0.2]
    ce = CachedEmbedder(inner=inner, cache=LRUCache(max_size=10))
    assert ce.embed("hello") == [0.1, 0.2]
    inner.embed.assert_called_once_with("hello")


def test_cached_embedder_skips_inner_on_hit():
    inner = MagicMock()
    inner.embed.return_value = [0.1, 0.2]
    ce = CachedEmbedder(inner=inner, cache=LRUCache(max_size=10))
    ce.embed("hello")
    ce.embed("hello")
    assert inner.embed.call_count == 1


def test_cached_embedder_batch_partial_hit():
    inner = MagicMock()
    inner.embed_batch.return_value = [[0.3, 0.4]]
    cache = LRUCache(max_size=10)
    ce = CachedEmbedder(inner=inner, cache=cache)
    # warm cache for "a"
    inner.embed.return_value = [0.1, 0.2]
    ce.embed("a")
    # batch with one hit + one miss
    inner.embed_batch.reset_mock()
    result = ce.embed_batch(["a", "b"])
    assert result == [[0.1, 0.2], [0.3, 0.4]]
    # only the miss should be sent to inner
    inner.embed_batch.assert_called_once_with(["b"])
```

- [ ] **Step 6: 테스트 실패 확인**

Run: `pytest tests/shared/test_embedder_cache.py -v`
Expected: ImportError (`CachedEmbedder` 미존재).

- [ ] **Step 7: CachedEmbedder 구현**

`shared/observability/cache.py`에 추가:
```python
class CachedEmbedder:
    """Decorator over an Embedder-like object (duck-typed: embed + embed_batch)."""

    def __init__(self, inner, cache: LRUCache) -> None:
        self._inner = inner
        self._cache = cache

    @staticmethod
    def _key(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def embed(self, text: str) -> list[float]:
        k = self._key(text)
        cached = self._cache.get(k)
        if cached is not None:
            return cached
        v = self._inner.embed(text)
        self._cache.set(k, v)
        return v

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        results: list[list[float] | None] = [None] * len(texts)
        missing_indices: list[int] = []
        missing_texts: list[str] = []
        for i, t in enumerate(texts):
            cached = self._cache.get(self._key(t))
            if cached is not None:
                results[i] = cached
            else:
                missing_indices.append(i)
                missing_texts.append(t)
        if missing_texts:
            fresh = self._inner.embed_batch(missing_texts)
            for idx, vec, txt in zip(missing_indices, fresh, missing_texts):
                results[idx] = vec
                self._cache.set(self._key(txt), vec)
        return results  # type: ignore[return-value]
```

- [ ] **Step 8: embedder 캐시 테스트 통과 확인**

Run: `pytest tests/shared/test_embedder_cache.py -v`
Expected: 3 PASSED.

- [ ] **Step 9: tests/shared/test_llm_cache.py 작성**

```python
from unittest.mock import MagicMock
from shared.observability.cache import LRUCache, CachedLLM


def test_cached_llm_calls_inner_on_miss():
    inner = MagicMock()
    inner.complete.return_value = "answer"
    cl = CachedLLM(inner=inner, cache=LRUCache(max_size=10), model_name="m1")
    assert cl.complete("prompt") == "answer"
    inner.complete.assert_called_once_with("prompt")


def test_cached_llm_skips_inner_on_hit():
    inner = MagicMock()
    inner.complete.return_value = "answer"
    cl = CachedLLM(inner=inner, cache=LRUCache(max_size=10), model_name="m1")
    cl.complete("prompt")
    cl.complete("prompt")
    assert inner.complete.call_count == 1


def test_cached_llm_different_model_different_key():
    inner = MagicMock()
    inner.complete.return_value = "answer"
    cache = LRUCache(max_size=10)
    cl_a = CachedLLM(inner=inner, cache=cache, model_name="m-a")
    cl_b = CachedLLM(inner=inner, cache=cache, model_name="m-b")
    cl_a.complete("p")
    cl_b.complete("p")
    assert inner.complete.call_count == 2
```

- [ ] **Step 10: 테스트 실패 확인**

Run: `pytest tests/shared/test_llm_cache.py -v`
Expected: ImportError.

- [ ] **Step 11: CachedLLM 구현**

`shared/observability/cache.py`에 추가:
```python
from shared.llm.base import LLMClient


class CachedLLM(LLMClient):
    def __init__(self, inner: LLMClient, cache: LRUCache, model_name: str = "") -> None:
        self._inner = inner
        self._cache = cache
        self._model = model_name

    def _key(self, prompt: str) -> str:
        return hashlib.sha256((self._model + "::" + prompt).encode("utf-8")).hexdigest()

    def complete(self, prompt: str) -> str:
        k = self._key(prompt)
        cached = self._cache.get(k)
        if cached is not None:
            return cached
        v = self._inner.complete(prompt)
        self._cache.set(k, v)
        return v
```

- [ ] **Step 12: 모든 캐시 테스트 통과 확인**

Run: `pytest tests/shared/test_cache.py tests/shared/test_embedder_cache.py tests/shared/test_llm_cache.py -v`
Expected: 모두 PASSED.

- [ ] **Step 13: 커밋**

```bash
git add shared/observability/cache.py tests/shared/test_cache.py tests/shared/test_embedder_cache.py tests/shared/test_llm_cache.py
git commit -m "feat(observability): add LRUCache, CachedEmbedder, CachedLLM"
```

---

## Task 5: shared/observability/eval/ — metrics + Evaluator

**Files:**
- Create: `shared/observability/eval/__init__.py`
- Create: `shared/observability/eval/metrics.py`
- Create: `shared/observability/eval/evaluator.py`
- Create: `tests/shared/test_eval.py`

- [ ] **Step 1: tests/shared/test_eval.py 작성**

```python
from shared.observability.eval.metrics import recall_at_k, latency_ms
from shared.observability.eval.evaluator import Evaluator, EvalCase, EvalReport
from shared.observability.tracer import Span
from shared.models import Answer


def test_recall_at_k_hit():
    assert recall_at_k(["a.md", "b.md", "c.md"], "b.md", k=3) == 1.0


def test_recall_at_k_miss():
    assert recall_at_k(["a.md", "b.md"], "c.md", k=2) == 0.0


def test_recall_at_k_outside_k():
    assert recall_at_k(["a.md", "b.md", "c.md"], "c.md", k=2) == 0.0


def test_latency_ms_from_span():
    s = Span(name="x", started_at=10.0, ended_at=10.250)
    assert round(latency_ms(s)) == 250


def test_evaluator_runs_all_cases_and_records_metrics():
    cases = [
        EvalCase(question="q1", expected_keywords=["k1"], expected_source="a.md"),
        EvalCase(question="q2", expected_keywords=["k2"], expected_source="b.md"),
    ]

    def fake_workflow(q):
        if q == "q1":
            return Answer(text="k1 here", sources=["a.md"], trace=None)
        return Answer(text="k2 here", sources=["x.md"], trace=None)

    e = Evaluator()
    report = e.evaluate(fake_workflow, cases)

    assert isinstance(report, EvalReport)
    assert len(report.cases) == 2
    # case 1: source hit
    assert report.cases[0]["recall_at_k"] == 1.0
    # case 2: source miss
    assert report.cases[1]["recall_at_k"] == 0.0


def test_evaluator_continues_on_case_error():
    cases = [
        EvalCase(question="ok", expected_keywords=[], expected_source="a.md"),
        EvalCase(question="boom", expected_keywords=[], expected_source="b.md"),
    ]

    def workflow(q):
        if q == "boom":
            raise RuntimeError("nope")
        return Answer(text="ok", sources=["a.md"], trace=None)

    report = Evaluator().evaluate(workflow, cases)
    assert report.cases[0].get("error") is None
    assert report.cases[1].get("error") == "RuntimeError"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/shared/test_eval.py -v`
Expected: ImportError.

- [ ] **Step 3: shared/observability/eval/__init__.py 생성**

빈 파일.

- [ ] **Step 4: metrics.py 작성**

`shared/observability/eval/metrics.py`:
```python
from shared.observability.tracer import Span


def recall_at_k(retrieved_sources: list[str], expected_source: str, k: int) -> float:
    return 1.0 if expected_source in retrieved_sources[:k] else 0.0


def latency_ms(span: Span) -> float:
    return (span.ended_at - span.started_at) * 1000.0
```

- [ ] **Step 5: evaluator.py 작성**

`shared/observability/eval/evaluator.py`:
```python
from dataclasses import dataclass, field
from typing import Callable

from shared.models import Answer
from shared.observability.eval.metrics import recall_at_k


@dataclass
class EvalCase:
    question: str
    expected_keywords: list[str]
    expected_source: str


@dataclass
class EvalReport:
    cases: list[dict] = field(default_factory=list)
    aggregate: dict = field(default_factory=dict)


class Evaluator:
    def __init__(self, k: int = 5) -> None:
        self._k = k

    def evaluate(
        self, workflow: Callable[[str], Answer], cases: list[EvalCase]
    ) -> EvalReport:
        results: list[dict] = []
        for case in cases:
            entry: dict = {
                "question": case.question,
                "expected_source": case.expected_source,
            }
            try:
                ans = workflow(case.question)
                entry["answer"] = ans.text
                entry["sources"] = ans.sources
                entry["recall_at_k"] = recall_at_k(ans.sources, case.expected_source, self._k)
            except Exception as e:
                entry["error"] = type(e).__name__
            results.append(entry)

        recalls = [r["recall_at_k"] for r in results if "recall_at_k" in r]
        agg = {
            "mean_recall_at_k": sum(recalls) / len(recalls) if recalls else 0.0,
            "n_cases": len(cases),
            "n_errors": sum(1 for r in results if "error" in r),
        }
        return EvalReport(cases=results, aggregate=agg)
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `pytest tests/shared/test_eval.py -v`
Expected: 6 PASSED.

- [ ] **Step 7: 커밋**

```bash
git add shared/observability/eval/ tests/shared/test_eval.py
git commit -m "feat(observability): add eval metrics and Evaluator"
```

---

## Task 6: shared/loader/ — DocumentLoader + MarkdownLoader

**Files:**
- Create: `shared/loader/__init__.py`
- Create: `shared/loader/base.py`
- Create: `shared/loader/markdown_loader.py`
- Create: `tests/shared/test_loader.py`

- [ ] **Step 1: tests/shared/test_loader.py 작성**

```python
import pytest
from shared.loader import MarkdownLoader
from shared.loader.base import DocumentLoader


def test_loader_implements_abc():
    assert issubclass(MarkdownLoader, DocumentLoader)


def test_loader_reads_md_files(tmp_path):
    (tmp_path / "a.md").write_text("hello A", encoding="utf-8")
    (tmp_path / "b.md").write_text("hello B", encoding="utf-8")
    docs = MarkdownLoader().load(str(tmp_path))
    sources = sorted(d.source for d in docs)
    assert sources == ["a.md", "b.md"]
    contents = {d.source: d.text for d in docs}
    assert contents["a.md"] == "hello A"
    assert contents["b.md"] == "hello B"


def test_loader_ignores_non_md_files(tmp_path):
    (tmp_path / "a.md").write_text("md content", encoding="utf-8")
    (tmp_path / "b.txt").write_text("not md", encoding="utf-8")
    docs = MarkdownLoader().load(str(tmp_path))
    assert [d.source for d in docs] == ["a.md"]


def test_loader_empty_dir(tmp_path):
    assert MarkdownLoader().load(str(tmp_path)) == []


def test_loader_missing_dir_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        MarkdownLoader().load(str(tmp_path / "nope"))
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/shared/test_loader.py -v`
Expected: ImportError.

- [ ] **Step 3: base.py 작성**

`shared/loader/base.py`:
```python
from abc import ABC, abstractmethod

from shared.models import Document


class DocumentLoader(ABC):
    @abstractmethod
    def load(self, path: str) -> list[Document]: ...
```

- [ ] **Step 4: markdown_loader.py 작성**

`shared/loader/markdown_loader.py`:
```python
import os

from shared.loader.base import DocumentLoader
from shared.models import Document


class MarkdownLoader(DocumentLoader):
    def load(self, path: str) -> list[Document]:
        if not os.path.isdir(path):
            raise FileNotFoundError(path)
        docs: list[Document] = []
        for filename in sorted(os.listdir(path)):
            if not filename.endswith(".md"):
                continue
            full = os.path.join(path, filename)
            with open(full, encoding="utf-8") as f:
                text = f.read()
            docs.append(Document(text=text, source=filename))
        return docs
```

- [ ] **Step 5: __init__.py 작성**

`shared/loader/__init__.py`:
```python
from shared.loader.base import DocumentLoader
from shared.loader.markdown_loader import MarkdownLoader

__all__ = ["DocumentLoader", "MarkdownLoader"]
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `pytest tests/shared/test_loader.py -v`
Expected: 5 PASSED.

- [ ] **Step 7: 커밋**

```bash
git add shared/loader/ tests/shared/test_loader.py
git commit -m "feat(loader): add DocumentLoader ABC and MarkdownLoader"
```

---

## Task 7: shared/chunker/ — Chunker + FixedSizeChunker

**Files:**
- Create: `shared/chunker/__init__.py`
- Create: `shared/chunker/base.py`
- Create: `shared/chunker/fixed_size_chunker.py`
- Create: `tests/shared/test_chunker.py`

- [ ] **Step 1: tests/shared/test_chunker.py 작성**

```python
from shared.chunker import FixedSizeChunker
from shared.chunker.base import Chunker
from shared.models import Document


def test_chunker_implements_abc():
    assert issubclass(FixedSizeChunker, Chunker)


def test_chunk_short_doc_single_chunk():
    chunker = FixedSizeChunker(chunk_size=100, chunk_overlap=10)
    doc = Document(text="hello world", source="a.md")
    chunks = chunker.chunk(doc)
    assert len(chunks) == 1
    assert chunks[0].text == "hello world"
    assert chunks[0].source == "a.md"
    assert chunks[0].chunk_id  # non-empty uuid


def test_chunk_long_doc_multiple_chunks_no_overlap():
    text = "x" * 250
    chunker = FixedSizeChunker(chunk_size=100, chunk_overlap=0)
    chunks = chunker.chunk(Document(text=text, source="a.md"))
    assert len(chunks) == 3
    assert all(c.source == "a.md" for c in chunks)
    assert chunks[0].text == "x" * 100
    assert chunks[1].text == "x" * 100
    assert chunks[2].text == "x" * 50


def test_chunk_long_doc_with_overlap():
    text = "x" * 250
    chunker = FixedSizeChunker(chunk_size=100, chunk_overlap=20)
    chunks = chunker.chunk(Document(text=text, source="a.md"))
    # stride = 80, so starts at 0, 80, 160, 240
    assert len(chunks) == 4


def test_chunk_empty_doc():
    chunker = FixedSizeChunker(chunk_size=100, chunk_overlap=0)
    assert chunker.chunk(Document(text="", source="a.md")) == []


def test_chunk_strips_whitespace():
    chunker = FixedSizeChunker(chunk_size=100, chunk_overlap=0)
    chunks = chunker.chunk(Document(text="   hi   ", source="a.md"))
    assert len(chunks) == 1
    assert chunks[0].text == "hi"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/shared/test_chunker.py -v`
Expected: ImportError.

- [ ] **Step 3: base.py 작성**

`shared/chunker/base.py`:
```python
from abc import ABC, abstractmethod

from shared.models import Chunk, Document


class Chunker(ABC):
    @abstractmethod
    def chunk(self, doc: Document) -> list[Chunk]: ...
```

- [ ] **Step 4: fixed_size_chunker.py 작성**

`shared/chunker/fixed_size_chunker.py`:
```python
import uuid

from shared.chunker.base import Chunker
from shared.models import Chunk, Document


class FixedSizeChunker(Chunker):
    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50) -> None:
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be < chunk_size")
        self._size = chunk_size
        self._overlap = chunk_overlap

    def chunk(self, doc: Document) -> list[Chunk]:
        text = doc.text
        chunks: list[Chunk] = []
        start = 0
        stride = self._size - self._overlap
        while start < len(text):
            end = min(start + self._size, len(text))
            piece = text[start:end].strip()
            if piece:
                chunks.append(
                    Chunk(
                        text=piece,
                        source=doc.source,
                        chunk_id=str(uuid.uuid4()),
                        metadata=dict(doc.metadata),
                    )
                )
            start += stride
        return chunks
```

- [ ] **Step 5: __init__.py 작성**

`shared/chunker/__init__.py`:
```python
from shared.chunker.base import Chunker
from shared.chunker.fixed_size_chunker import FixedSizeChunker

__all__ = ["Chunker", "FixedSizeChunker"]
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `pytest tests/shared/test_chunker.py -v`
Expected: 6 PASSED.

- [ ] **Step 7: 커밋**

```bash
git add shared/chunker/ tests/shared/test_chunker.py
git commit -m "feat(chunker): add Chunker ABC and FixedSizeChunker"
```

---

## Task 8: shared/embedder/ — Embedder ABC + SentenceTransformerEmbedder + langchain adapter

**Files:**
- Create: `shared/embedder/__init__.py`
- Create: `shared/embedder/base.py`
- Create: `shared/embedder/sentence_transformer_embedder.py`
- Create: `shared/embedder/adapters/__init__.py`
- Create: `shared/embedder/adapters/langchain_adapter.py`
- Create: `tests/shared/test_embedder.py`
- Modify: `shared/observability/cache.py` (CachedEmbedder를 Embedder ABC subclass로)

기존 `shared/retriever/embedding.py`는 **삭제하지 않고** Task 9에서 함께 정리(주석된 워크플로우만 참조).

- [ ] **Step 1: tests/shared/test_embedder.py 작성**

```python
import pytest
from shared.embedder.base import Embedder


class _StubEmbedder(Embedder):
    def embed(self, text: str) -> list[float]:
        return [float(len(text))]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


def test_embedder_is_abc():
    with pytest.raises(TypeError):
        Embedder()  # cannot instantiate ABC


def test_stub_embedder_works():
    e = _StubEmbedder()
    assert e.embed("hi") == [2.0]
    assert e.embed_batch(["a", "bb"]) == [[1.0], [2.0]]


def test_sentence_transformer_embedder_shape():
    pytest.importorskip("sentence_transformers")
    from shared.embedder import SentenceTransformerEmbedder

    e = SentenceTransformerEmbedder("paraphrase-multilingual-MiniLM-L12-v2")
    v = e.embed("hello world")
    assert isinstance(v, list)
    assert len(v) > 0
    batch = e.embed_batch(["hello", "world"])
    assert len(batch) == 2
    assert len(batch[0]) == len(v)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/shared/test_embedder.py -v`
Expected: ImportError.

- [ ] **Step 3: shared/embedder/base.py 작성**

```python
from abc import ABC, abstractmethod


class Embedder(ABC):
    @abstractmethod
    def embed(self, text: str) -> list[float]: ...

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...
```

- [ ] **Step 4: sentence_transformer_embedder.py 작성**

```python
from sentence_transformers import SentenceTransformer

from shared.embedder.base import Embedder


class SentenceTransformerEmbedder(Embedder):
    def __init__(self, model_name: str) -> None:
        self._model = SentenceTransformer(model_name)

    def embed(self, text: str) -> list[float]:
        return self._model.encode(text).tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts).tolist()
```

- [ ] **Step 5: langchain adapter 작성**

기존 `shared/llm/adapters/langchain_adapter.py` 패턴을 따라 `shared/embedder/adapters/langchain_adapter.py`:

```python
from typing import List

from shared.embedder.base import Embedder


class LangChainEmbeddingsAdapter:
    """LangChain Embeddings 인터페이스(embed_documents/embed_query)를 우리 Embedder에 어댑트."""

    def __init__(self, embedder: Embedder) -> None:
        self._embedder = embedder

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self._embedder.embed_batch(texts)

    def embed_query(self, text: str) -> List[float]:
        return self._embedder.embed(text)
```

`shared/embedder/adapters/__init__.py`:
```python
from shared.embedder.adapters.langchain_adapter import LangChainEmbeddingsAdapter

__all__ = ["LangChainEmbeddingsAdapter"]
```

- [ ] **Step 6: shared/embedder/__init__.py 작성**

```python
from shared.embedder.base import Embedder
from shared.embedder.sentence_transformer_embedder import SentenceTransformerEmbedder

__all__ = ["Embedder", "SentenceTransformerEmbedder"]
```

- [ ] **Step 7: CachedEmbedder를 Embedder ABC subclass로 격상**

`shared/observability/cache.py`에서 `CachedEmbedder` 클래스 선언을 다음으로 변경:

```python
from shared.embedder.base import Embedder

class CachedEmbedder(Embedder):
    ...
```

(import는 파일 상단에 추가; 클래스 시그니처만 `Embedder` 상속하도록 바꿈. 메서드는 그대로 — 이미 동일 시그니처.)

- [ ] **Step 8: 모든 관련 테스트 통과 확인**

Run: `pytest tests/shared/test_embedder.py tests/shared/test_embedder_cache.py -v`
Expected: 모두 PASSED. `test_sentence_transformer_embedder_shape`는 sentence-transformers 미설치 시 skip.

- [ ] **Step 9: 커밋**

```bash
git add shared/embedder/ shared/observability/cache.py tests/shared/test_embedder.py
git commit -m "feat(embedder): add Embedder ABC, SentenceTransformerEmbedder, langchain adapter"
```

---

## Task 9: shared/retriever/ 인터페이스화 + BasicRetriever, 기존 embedding.py/retriever.py 삭제

**Files:**
- Create: `shared/retriever/base.py`
- Create: `shared/retriever/basic_retriever.py`
- Modify: `shared/retriever/__init__.py`
- Delete: `shared/retriever/embedding.py`
- Delete: `shared/retriever/retriever.py`
- Modify: `tests/shared/test_retriever.py`

- [ ] **Step 1: tests/shared/test_retriever.py 교체**

기존 파일을 다음으로 덮어쓰기:

```python
from unittest.mock import MagicMock

from shared.models import Chunk, SearchResult
from shared.retriever import BasicRetriever
from shared.retriever.base import Retriever


def test_basic_retriever_implements_abc():
    assert issubclass(BasicRetriever, Retriever)


def test_basic_retriever_calls_embed_and_search():
    store = MagicMock()
    store.search.return_value = [
        SearchResult(
            chunk=Chunk(text="연차 15일", source="vacation.md", chunk_id="c1"),
            score=0.9,
        )
    ]
    embedder = MagicMock()
    embedder.embed.return_value = [0.1, 0.2, 0.3]

    r = BasicRetriever(store=store, embedder=embedder)
    results = r.retrieve("연차 며칠이야", top_k=3)

    embedder.embed.assert_called_once_with("연차 며칠이야")
    store.search.assert_called_once_with([0.1, 0.2, 0.3], top_k=3)
    assert len(results) == 1
    assert results[0].chunk.source == "vacation.md"


def test_basic_retriever_empty_results():
    store = MagicMock()
    store.search.return_value = []
    embedder = MagicMock()
    embedder.embed.return_value = [0.0]
    r = BasicRetriever(store=store, embedder=embedder)
    assert r.retrieve("anything") == []
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/shared/test_retriever.py -v`
Expected: ImportError.

- [ ] **Step 3: shared/retriever/base.py 작성**

```python
from abc import ABC, abstractmethod

from shared.models import SearchResult


class Retriever(ABC):
    @abstractmethod
    def retrieve(self, query: str, top_k: int = 5) -> list[SearchResult]: ...
```

- [ ] **Step 4: shared/retriever/basic_retriever.py 작성**

```python
from shared.embedder.base import Embedder
from shared.models import SearchResult
from shared.retriever.base import Retriever
from shared.vector_store.base import VectorStore


class BasicRetriever(Retriever):
    def __init__(self, store: VectorStore, embedder: Embedder) -> None:
        self._store = store
        self._embedder = embedder

    def retrieve(self, query: str, top_k: int = 5) -> list[SearchResult]:
        embedding = self._embedder.embed(query)
        return self._store.search(embedding, top_k=top_k)
```

- [ ] **Step 5: shared/retriever/__init__.py 작성**

```python
from shared.retriever.base import Retriever
from shared.retriever.basic_retriever import BasicRetriever

__all__ = ["Retriever", "BasicRetriever"]
```

- [ ] **Step 6: 기존 파일 삭제**

```bash
git rm shared/retriever/embedding.py shared/retriever/retriever.py
```

- [ ] **Step 7: 테스트 통과 확인 + 전체 pytest 깨진 곳 확인**

Run: `pytest -q`
Expected:
- `tests/shared/test_retriever.py`: PASS
- `tests/shared/test_indexer.py`: 아직 실패 (기존 시그니처 사용 중) — Task 11에서 수정
- 기존 deprecated workflow 테스트: 주석 처리되어 collect 안 됨
- 나머지: PASS

`test_indexer.py`만 실패해야 함. 다른 실패가 있으면 멈추고 점검.

- [ ] **Step 8: 커밋**

```bash
git add shared/retriever/ tests/shared/test_retriever.py
git commit -m "feat(retriever): interface-ize with Retriever ABC and BasicRetriever"
```

---

## Task 10: shared/reranker/ — Reranker ABC + NoOpReranker

**Files:**
- Create: `shared/reranker/__init__.py`
- Create: `shared/reranker/base.py`
- Create: `shared/reranker/noop_reranker.py`
- Create: `tests/shared/test_reranker.py`

- [ ] **Step 1: tests/shared/test_reranker.py 작성**

```python
from shared.models import Chunk, SearchResult
from shared.reranker import NoOpReranker
from shared.reranker.base import Reranker


def _sr(source: str, score: float) -> SearchResult:
    return SearchResult(
        chunk=Chunk(text="t", source=source, chunk_id=source), score=score
    )


def test_noop_implements_abc():
    assert issubclass(NoOpReranker, Reranker)


def test_noop_preserves_order():
    results = [_sr("a", 0.9), _sr("b", 0.8), _sr("c", 0.7)]
    out = NoOpReranker().rerank("q", results)
    assert [r.chunk.source for r in out] == ["a", "b", "c"]


def test_noop_truncates_to_top_k():
    results = [_sr(s, 0.5) for s in ["a", "b", "c", "d"]]
    out = NoOpReranker().rerank("q", results, top_k=2)
    assert [r.chunk.source for r in out] == ["a", "b"]


def test_noop_top_k_none_returns_all():
    results = [_sr(s, 0.5) for s in ["a", "b", "c"]]
    out = NoOpReranker().rerank("q", results, top_k=None)
    assert len(out) == 3


def test_noop_empty_input():
    assert NoOpReranker().rerank("q", []) == []
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/shared/test_reranker.py -v`
Expected: ImportError.

- [ ] **Step 3: base.py 작성**

`shared/reranker/base.py`:
```python
from abc import ABC, abstractmethod

from shared.models import SearchResult


class Reranker(ABC):
    @abstractmethod
    def rerank(
        self,
        query: str,
        results: list[SearchResult],
        top_k: int | None = None,
    ) -> list[SearchResult]: ...
```

- [ ] **Step 4: noop_reranker.py 작성**

`shared/reranker/noop_reranker.py`:
```python
from shared.models import SearchResult
from shared.reranker.base import Reranker


class NoOpReranker(Reranker):
    def rerank(
        self,
        query: str,
        results: list[SearchResult],
        top_k: int | None = None,
    ) -> list[SearchResult]:
        if top_k is None:
            return list(results)
        return list(results[:top_k])
```

- [ ] **Step 5: __init__.py 작성**

`shared/reranker/__init__.py`:
```python
from shared.reranker.base import Reranker
from shared.reranker.noop_reranker import NoOpReranker

__all__ = ["Reranker", "NoOpReranker"]
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `pytest tests/shared/test_reranker.py -v`
Expected: 5 PASSED.

- [ ] **Step 7: 커밋**

```bash
git add shared/reranker/ tests/shared/test_reranker.py
git commit -m "feat(reranker): add Reranker ABC and NoOpReranker"
```

---

## Task 11: shared/indexer/ 새 시그니처로 교체

**Files:**
- Modify: `shared/indexer/indexer.py`
- Modify: `tests/shared/test_indexer.py`

- [ ] **Step 1: tests/shared/test_indexer.py 교체**

기존 파일을 다음으로 덮어쓰기:

```python
from unittest.mock import MagicMock

from shared.indexer.indexer import Indexer
from shared.models import Chunk, Document


def test_indexer_composes_loader_chunker_embedder_store():
    loader = MagicMock()
    loader.load.return_value = [Document(text="hello world", source="a.md")]

    chunker = MagicMock()
    chunker.chunk.return_value = [
        Chunk(text="hello world", source="a.md", chunk_id="c1")
    ]

    embedder = MagicMock()
    embedder.embed_batch.return_value = [[0.1, 0.2, 0.3]]

    store = MagicMock()

    indexer = Indexer(loader=loader, chunker=chunker, embedder=embedder, store=store)
    count = indexer.index("/some/path")

    loader.load.assert_called_once_with("/some/path")
    chunker.chunk.assert_called_once()
    embedder.embed_batch.assert_called_once_with(["hello world"])
    store.add.assert_called_once()
    assert count == 1


def test_indexer_empty_docs_skips_store_add():
    loader = MagicMock()
    loader.load.return_value = []
    chunker = MagicMock()
    embedder = MagicMock()
    store = MagicMock()

    indexer = Indexer(loader=loader, chunker=chunker, embedder=embedder, store=store)
    count = indexer.index("/empty")

    assert count == 0
    chunker.chunk.assert_not_called()
    embedder.embed_batch.assert_not_called()
    store.add.assert_not_called()


def test_indexer_concatenates_chunks_from_multiple_docs():
    loader = MagicMock()
    loader.load.return_value = [
        Document(text="A", source="a.md"),
        Document(text="B", source="b.md"),
    ]
    chunker = MagicMock()
    chunker.chunk.side_effect = [
        [Chunk(text="A", source="a.md", chunk_id="ca")],
        [Chunk(text="B", source="b.md", chunk_id="cb")],
    ]
    embedder = MagicMock()
    embedder.embed_batch.return_value = [[0.1], [0.2]]
    store = MagicMock()

    Indexer(loader=loader, chunker=chunker, embedder=embedder, store=store).index("/p")

    embedder.embed_batch.assert_called_once_with(["A", "B"])
    assert store.add.call_count == 1
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/shared/test_indexer.py -v`
Expected: FAIL — 새 시그니처에 맞지 않음 (현 코드는 `vector_store=`, `embedding_service=`를 받음).

- [ ] **Step 3: shared/indexer/indexer.py 교체**

기존 내용을 다음으로 덮어쓰기:

```python
from shared.chunker.base import Chunker
from shared.embedder.base import Embedder
from shared.loader.base import DocumentLoader
from shared.vector_store.base import VectorStore


class Indexer:
    def __init__(
        self,
        loader: DocumentLoader,
        chunker: Chunker,
        embedder: Embedder,
        store: VectorStore,
    ) -> None:
        self._loader = loader
        self._chunker = chunker
        self._embedder = embedder
        self._store = store

    def index(self, path: str) -> int:
        docs = self._loader.load(path)
        chunks = [c for d in docs for c in self._chunker.chunk(d)]
        if not chunks:
            return 0
        embeddings = self._embedder.embed_batch([c.text for c in chunks])
        self._store.add(chunks, embeddings)
        return len(chunks)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/shared/test_indexer.py -v`
Expected: 3 PASSED.

- [ ] **Step 5: 전체 pytest 다시 깨끗한지 확인**

Run: `pytest -q`
Expected: 모두 PASS. 깨지는 게 있으면 Task 9~10의 import를 정리.

- [ ] **Step 6: 커밋**

```bash
git add shared/indexer/indexer.py tests/shared/test_indexer.py
git commit -m "refactor(indexer): take loader/chunker/embedder/store, delegate steps"
```

---

## Task 12: shared/orchestrator/ — Context + Step + Pipeline

**Files:**
- Create: `shared/orchestrator/__init__.py`
- Create: `shared/orchestrator/context.py`
- Create: `shared/orchestrator/step.py`
- Create: `shared/orchestrator/pipeline.py`
- Create: `tests/shared/test_orchestrator.py`

- [ ] **Step 1: tests/shared/test_orchestrator.py 작성**

```python
import pytest

from shared.observability.tracer import Tracer
from shared.orchestrator import Context, Pipeline, Step


class _SetAnswer(Step):
    name = "set_answer"

    def __init__(self, value: str) -> None:
        self._value = value

    def run(self, ctx: Context) -> Context:
        ctx.answer_text = self._value
        return ctx


class _AppendMeta(Step):
    name = "append_meta"

    def run(self, ctx: Context) -> Context:
        ctx.metadata.setdefault("visited", []).append(self.name)
        return ctx


class _Boom(Step):
    name = "boom"

    def run(self, ctx: Context) -> Context:
        raise RuntimeError("kaboom")


def test_context_defaults():
    ctx = Context(query="q")
    assert ctx.query == "q"
    assert ctx.chunks == []
    assert ctx.answer_text is None
    assert ctx.metadata == {}


def test_pipeline_runs_steps_in_order():
    p = Pipeline(steps=[_AppendMeta(), _SetAnswer("hello")])
    ctx = p.run(Context(query="q"))
    assert ctx.metadata["visited"] == ["append_meta"]
    assert ctx.answer_text == "hello"


def test_pipeline_with_tracer_records_span_per_step():
    tracer = Tracer()
    p = Pipeline(steps=[_AppendMeta(), _SetAnswer("ok")], tracer=tracer)
    p.run(Context(query="q"))
    assert [s.name for s in tracer.spans] == ["append_meta", "set_answer"]


def test_pipeline_records_error_in_span_and_reraises():
    tracer = Tracer()
    p = Pipeline(steps=[_Boom()], tracer=tracer)
    with pytest.raises(RuntimeError):
        p.run(Context(query="q"))
    assert tracer.spans[0].metadata.get("status") == "error"
    assert tracer.spans[0].metadata.get("error") == "RuntimeError"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/shared/test_orchestrator.py -v`
Expected: ImportError.

- [ ] **Step 3: context.py 작성**

`shared/orchestrator/context.py`:
```python
from dataclasses import dataclass, field

from shared.models import SearchResult


@dataclass
class Context:
    query: str
    chunks: list[SearchResult] = field(default_factory=list)
    answer_text: str | None = None
    metadata: dict = field(default_factory=dict)
```

- [ ] **Step 4: step.py 작성**

`shared/orchestrator/step.py`:
```python
from abc import ABC, abstractmethod

from shared.orchestrator.context import Context


class Step(ABC):
    name: str = "step"

    @abstractmethod
    def run(self, ctx: Context) -> Context: ...
```

- [ ] **Step 5: pipeline.py 작성**

`shared/orchestrator/pipeline.py`:
```python
from shared.observability.tracer import Tracer
from shared.orchestrator.context import Context
from shared.orchestrator.step import Step


class Pipeline:
    def __init__(self, steps: list[Step], tracer: Tracer | None = None) -> None:
        self._steps = steps
        self._tracer = tracer

    def run(self, ctx: Context) -> Context:
        for step in self._steps:
            if self._tracer is not None:
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

- [ ] **Step 6: __init__.py 작성**

`shared/orchestrator/__init__.py`:
```python
from shared.orchestrator.context import Context
from shared.orchestrator.pipeline import Pipeline
from shared.orchestrator.step import Step

__all__ = ["Context", "Pipeline", "Step"]
```

- [ ] **Step 7: 테스트 통과 확인**

Run: `pytest tests/shared/test_orchestrator.py -v`
Expected: 4 PASSED.

- [ ] **Step 8: 커밋**

```bash
git add shared/orchestrator/ tests/shared/test_orchestrator.py
git commit -m "feat(orchestrator): add Context, Step ABC, Pipeline with tracer"
```

---

## Task 13: workflows/pipeline/ — Step 구현체 + qa.py + prompts.py

> 디렉터리 이름은 `pipeline` (Python identifier 규칙상 숫자 prefix 안 씀). 기존 deprecated workflow와의 번호 일관성보다 정상 import path가 우선.

**Files:**
- Create: `workflows/pipeline/__init__.py`
- Create: `workflows/pipeline/prompts.py`
- Create: `workflows/pipeline/steps.py`
- Create: `workflows/pipeline/qa.py`
- Create: `tests/workflows/test_04_pipeline.py`

- [ ] **Step 1: tests/workflows/test_04_pipeline.py 작성 (실패 테스트)**

```python
from unittest.mock import MagicMock, patch

from shared.models import Answer, Chunk, SearchResult


def _make_result(source: str, text: str = "text") -> SearchResult:
    return SearchResult(
        chunk=Chunk(text=text, source=source, chunk_id=source), score=0.9
    )


def test_pipeline_qa_end_to_end():
    fake_retriever = MagicMock()
    fake_retriever.retrieve.return_value = [
        _make_result("a.md", "연차 15일"),
        _make_result("a.md", "연차 사용법"),  # 같은 source 두 개
        _make_result("b.md", "휴가 정책"),
    ]
    fake_reranker = MagicMock()
    fake_reranker.rerank.side_effect = lambda q, r, top_k=None: r[: (top_k or len(r))]
    fake_llm = MagicMock()
    fake_llm.complete.return_value = "연차는 15일입니다."

    from workflows.pipeline import qa as qa_mod

    with patch.object(qa_mod, "_build_components") as build:
        build.return_value = (fake_retriever, fake_reranker, fake_llm)
        ans: Answer = qa_mod.run("연차 며칠?")

    assert ans.text == "연차는 15일입니다."
    # sources deduped
    assert sorted(ans.sources) == ["a.md", "b.md"]
    # trace contains 3 step names
    names = [s["name"] for s in ans.trace or []]
    assert names == ["retrieve", "rerank", "generate"]
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/workflows/test_04_pipeline.py -v`
Expected: ModuleNotFoundError (`workflows.pipeline` 미존재).

- [ ] **Step 3: 디렉터리 + 빈 `__init__.py` 생성**

```bash
mkdir -p workflows/pipeline
touch workflows/pipeline/__init__.py
```

- [ ] **Step 4: workflows/pipeline/prompts.py 작성**

```python
QA_PROMPT = """\
다음 문서를 참고하여 질문에 한국어로 답하세요.

문서:
{context}

질문: {question}
답변:"""
```

- [ ] **Step 5: workflows/pipeline/steps.py 작성**

```python
from shared.llm.base import LLMClient
from shared.orchestrator import Context, Step
from shared.reranker.base import Reranker
from shared.retriever.base import Retriever


class RetrieveStep(Step):
    name = "retrieve"

    def __init__(self, retriever: Retriever, top_k: int = 10) -> None:
        self._retriever = retriever
        self._top_k = top_k

    def run(self, ctx: Context) -> Context:
        ctx.chunks = self._retriever.retrieve(ctx.query, top_k=self._top_k)
        return ctx


class RerankStep(Step):
    name = "rerank"

    def __init__(self, reranker: Reranker, top_k: int = 5) -> None:
        self._reranker = reranker
        self._top_k = top_k

    def run(self, ctx: Context) -> Context:
        ctx.chunks = self._reranker.rerank(ctx.query, ctx.chunks, top_k=self._top_k)
        return ctx


class GenerateStep(Step):
    name = "generate"

    def __init__(self, llm: LLMClient, prompt_template: str) -> None:
        self._llm = llm
        self._template = prompt_template

    def run(self, ctx: Context) -> Context:
        context_text = "\n\n".join(c.chunk.text for c in ctx.chunks)
        prompt = self._template.format(context=context_text, question=ctx.query)
        ctx.answer_text = self._llm.complete(prompt)
        return ctx
```

- [ ] **Step 6: workflows/pipeline/qa.py 작성**

```python
from shared.config import load_config
from shared.embedder import SentenceTransformerEmbedder
from shared.llm.factory import create_llm
from shared.models import Answer
from shared.observability.cache import CachedEmbedder, CachedLLM, LRUCache
from shared.observability.tracer import Tracer
from shared.orchestrator import Context, Pipeline
from shared.reranker import NoOpReranker
from shared.retriever import BasicRetriever
from shared.vector_store.factory import create_vector_store

from workflows.pipeline.prompts import QA_PROMPT
from workflows.pipeline.steps import GenerateStep, RerankStep, RetrieveStep


def _build_components():
    config = load_config()
    embedder = CachedEmbedder(
        SentenceTransformerEmbedder(config.embedding_model),
        LRUCache(max_size=4096),
    )
    store = create_vector_store(config)
    retriever = BasicRetriever(store=store, embedder=embedder)
    reranker = NoOpReranker()
    llm = CachedLLM(
        create_llm(config),
        LRUCache(max_size=512),
        model_name=config.llm_model,
    )
    return retriever, reranker, llm


def run(question: str) -> Answer:
    retriever, reranker, llm = _build_components()
    tracer = Tracer()
    pipeline = Pipeline(
        steps=[
            RetrieveStep(retriever, top_k=10),
            RerankStep(reranker, top_k=5),
            GenerateStep(llm, QA_PROMPT),
        ],
        tracer=tracer,
    )
    ctx = pipeline.run(Context(query=question))
    sources = sorted({c.chunk.source for c in ctx.chunks})
    return Answer(
        text=ctx.answer_text or "",
        sources=sources,
        trace=tracer.dump(),
    )
```

- [ ] **Step 7: 테스트 통과 확인**

Run: `pytest tests/workflows/test_04_pipeline.py -v`
Expected: 1 PASSED.

- [ ] **Step 8: 커밋**

```bash
git add workflows/pipeline/ tests/workflows/test_04_pipeline.py
git commit -m "feat(workflow): add pipeline workflow with Retrieve/Rerank/Generate steps"
```

---

## Task 14: main.py에 `pipeline` mode 등록

**Files:**
- Modify: `main.py`

- [ ] **Step 1: main.py 갱신**

다음 내용으로 전체 교체:

```python
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
    from evals.runner import print_comparison, run_all

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
```

- [ ] **Step 2: smoke test — import 만 검증**

Run: `python3 -c "import main; print('ok')"`
Expected: `ok` 출력. (API 키 없어도 import는 통과.)

- [ ] **Step 3: 커밋**

```bash
git add main.py
git commit -m "feat(main): wire new Indexer and pipeline workflow into CLI"
```

---

## Task 15: evals/runner.py를 Evaluator 사용으로 리팩토링

**Files:**
- Modify: `evals/runner.py`

- [ ] **Step 1: 새 runner.py 작성**

`evals/runner.py` 전체 교체:

```python
import os
import time
from typing import Any

import yaml

from shared.models import Answer
from shared.observability.eval.evaluator import EvalCase, Evaluator


def _load_workflow_run():
    from workflows.pipeline.qa import run
    return run


def run_all(question: str) -> dict[str, dict[str, Any]]:
    """단일 질문을 pipeline 워크플로우로 실행 (deprecated 워크플로우 제거 후)."""
    run = _load_workflow_run()
    start = time.time()
    answer: Answer = run(question)
    elapsed = time.time() - start
    return {"pipeline": {"answer": answer, "elapsed_sec": round(elapsed, 2)}}


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


def run_eval(yaml_path: str | None = None) -> None:
    """questions.yaml 전체를 Evaluator로 채점하고 결과 출력."""
    raw = load_questions(yaml_path)
    cases = [
        EvalCase(
            question=q["question"],
            expected_keywords=q.get("expected_keywords", []),
            expected_source=q.get("expected_source", ""),
        )
        for q in raw
    ]
    run = _load_workflow_run()
    report = Evaluator(k=5).evaluate(run, cases)

    print("\n=== EVAL REPORT ===")
    for c in report.cases:
        line = f"Q: {c['question']!s:<40}"
        if "error" in c:
            line += f"  ERROR: {c['error']}"
        else:
            line += f"  recall@5={c['recall_at_k']:.2f}  src={c.get('sources')}"
        print(line)
    print(f"\nAggregate: {report.aggregate}")
```

- [ ] **Step 2: smoke test — import 통과 확인**

Run: `python3 -c "from evals.runner import run_all, run_eval; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: 커밋**

```bash
git add evals/runner.py
git commit -m "refactor(evals): use Evaluator and target pipeline workflow only"
```

---

## Task 16: 전체 검증

- [ ] **Step 1: 전체 pytest 통과 확인**

Run: `pytest -q`
Expected: 모든 테스트 PASS. deprecated workflow 테스트는 collect 안 됨.

만약 실패가 있으면 stop & diagnose.

- [ ] **Step 2: build-index smoke run**

(.env에 OPENAI_API_KEY 등 설정 후)

Run: `python3 main.py --build-index`
Expected: `인덱싱 완료: N개 청크 (.../docs)` 출력.

- [ ] **Step 3: pipeline smoke run**

Run: `python3 main.py --mode pipeline -q "연차는 며칠이야?"`
Expected:
- `답변: ...` 출력
- `출처: ...` 출력
- `[trace — 3단계]` 다음에 `retrieve`, `rerank`, `generate` 3개 span 출력

- [ ] **Step 4: eval smoke run (선택, 외부 API 필요)**

Run: `python3 -c "from evals.runner import run_eval; run_eval()"`
Expected: `=== EVAL REPORT ===` 다음에 questions.yaml의 5개 질문 각각에 대한 `recall@5` 점수 + 집계 출력.

- [ ] **Step 5: 마무리 커밋 (필요 시)**

특별한 변경 없으면 skip. tag로 마일스톤 표시:

```bash
git tag -a v0.2-architecture-improvement -m "RAG architecture per PRD #1안"
```

---

## 완료 기준

- 모든 Task의 모든 Step 체크
- `pytest -q` 전체 PASS
- `main.py --build-index`, `main.py --mode pipeline -q "..."` 동작
- `evals/runner.run_eval()` 실행 시 recall@5 출력
- `git log` 확인 시 Task 단위로 커밋이 분리됨
