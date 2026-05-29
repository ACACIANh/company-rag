# Project Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `graphs/` + `shared/` 구조를 `plan/plan.md` 기준의 `app/` 구조로 재편하고 AgentState(TypedDict)를 채택한다.

**Architecture:** `app/graph/`가 LangGraph 워크플로우를 소유하고, `app/ingestion/`이 문서 인덱싱을, `app/api/`가 FastAPI 엔드포인트를 담당한다. `shared/`는 ABC + 구현체 + Adapter만 남긴다.

**Tech Stack:** Python 3.11+, LangGraph, LangChain, FastAPI, pytest

---

## 파일 맵

| 작업 | 생성/수정/삭제 |
|---|---|
| Task 1 | Create: `app/__init__.py`, `app/graph/__init__.py`, `app/graph/nodes/__init__.py`, `app/ingestion/__init__.py`, `app/tools/__init__.py`, `app/api/__init__.py` |
| Task 2 | Create: `app/graph/state.py`, `tests/app/__init__.py`, `tests/app/graph/__init__.py`, `tests/app/graph/test_state.py` |
| Task 3 | Create: `app/graph/nodes/retrieve.py`, `tests/app/graph/nodes/__init__.py`, `tests/app/graph/nodes/test_retrieve.py` |
| Task 4 | Create: `app/graph/prompts.py`, `app/graph/nodes/generate.py`, `tests/app/graph/nodes/test_generate.py` |
| Task 5 | Create: `app/graph/edges.py` |
| Task 6 | Create: `app/graph/builder.py`, `tests/app/graph/test_builder.py` |
| Task 7 | Create: `app/ingestion/chunker.py`, `app/ingestion/embedder.py`, `app/ingestion/indexer.py`, `tests/app/ingestion/__init__.py`, `tests/app/ingestion/test_ingestion.py` |
| Task 8 | Modify: `requirements.txt` / Create: `app/api/chat.py`, `tests/app/api/__init__.py`, `tests/app/api/test_chat.py` |
| Task 9 | Modify: `scripts/chat_rag_basic.py`, `scripts/build_index.py`, `scripts/eval_rag_basic.py` |
| Task 10 | Create: `tests/eval/__init__.py`, `tests/eval/runner.py`, `tests/eval/questions.yaml` / Delete: `eval_suite/` |
| Task 11 | Delete: `graphs/` / Modify: `CLAUDE.md` |

---

### Task 1: app/ 패키지 스캐폴딩

**Files:**
- Create: `app/__init__.py` 외 6개 `__init__.py`

- [ ] **Step 1: 디렉토리와 __init__.py 생성**

```bash
mkdir -p app/graph/nodes app/ingestion app/tools app/api
touch app/__init__.py app/graph/__init__.py app/graph/nodes/__init__.py
touch app/ingestion/__init__.py app/tools/__init__.py app/api/__init__.py
mkdir -p tests/app/graph/nodes tests/app/ingestion tests/app/api
touch tests/app/__init__.py tests/app/graph/__init__.py tests/app/graph/nodes/__init__.py
touch tests/app/ingestion/__init__.py tests/app/api/__init__.py
```

- [ ] **Step 2: 구조 확인**

```bash
find app tests/app -name "*.py" | sort
```
Expected: 각 디렉토리에 `__init__.py` 존재 확인

- [ ] **Step 3: Commit**

```bash
git add app/ tests/app/
git commit -m "chore: scaffold app/ and tests/app/ package structure"
```

---

### Task 2: app/graph/state.py — AgentState

**Files:**
- Create: `app/graph/state.py`
- Test: `tests/app/graph/test_state.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/app/graph/test_state.py`:
```python
from typing import get_type_hints
from app.graph.state import AgentState


def test_agent_state_has_required_fields():
    hints = get_type_hints(AgentState, include_extras=True)
    required = {"question", "documents", "answer", "citations",
                "chat_history", "retry_count", "relevance_score",
                "hallucination_passed", "rewritten_question", "route"}
    assert required.issubset(hints.keys())


def test_agent_state_instantiation():
    state: AgentState = {
        "question": "테스트",
        "rewritten_question": "",
        "chat_history": [],
        "route": "doc_search",
        "documents": [],
        "relevance_score": 0.0,
        "retry_count": 0,
        "answer": "",
        "citations": [],
        "hallucination_passed": False,
    }
    assert state["question"] == "테스트"
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/app/graph/test_state.py -v
```
Expected: `ModuleNotFoundError: No module named 'app.graph.state'`

- [ ] **Step 3: AgentState 구현**

`app/graph/state.py`:
```python
from operator import add
from typing import Annotated, Literal, TypedDict

from shared.models import SearchResult


class AgentState(TypedDict):
    question: str
    rewritten_question: str
    chat_history: list[dict]
    route: Literal["doc_search", "tool_call", "web_search"]
    documents: Annotated[list[SearchResult], add]
    relevance_score: float
    retry_count: int
    answer: str
    citations: list[str]
    hallucination_passed: bool
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/app/graph/test_state.py -v
```
Expected: PASS 2개

- [ ] **Step 5: Commit**

```bash
git add app/graph/state.py tests/app/graph/test_state.py
git commit -m "feat(app): add AgentState TypedDict schema"
```

---

### Task 3: app/graph/nodes/retrieve.py

**Files:**
- Create: `app/graph/nodes/retrieve.py`
- Test: `tests/app/graph/nodes/test_retrieve.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/app/graph/nodes/test_retrieve.py`:
```python
from unittest.mock import MagicMock

from shared.models import Chunk, SearchResult
from app.graph.nodes.retrieve import retrieve_node


def _make_result(text: str, source: str) -> SearchResult:
    return SearchResult(chunk=Chunk(text=text, source=source), score=0.9)


def test_retrieve_node_returns_documents():
    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value = [_make_result("내용", "doc.md")]

    state = {"question": "테스트 질문"}
    result = retrieve_node(state, retriever=mock_retriever)

    assert "documents" in result
    assert len(result["documents"]) == 1
    mock_retriever.retrieve.assert_called_once_with("테스트 질문", top_k=5)


def test_retrieve_node_uses_question_field():
    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value = []

    retrieve_node({"question": "특정 질문"}, retriever=mock_retriever)
    mock_retriever.retrieve.assert_called_once_with("특정 질문", top_k=5)
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/app/graph/nodes/test_retrieve.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: retrieve_node 구현**

`app/graph/nodes/retrieve.py`:
```python
from shared.models import SearchResult
from shared.retriever.base import Retriever


def retrieve_node(state: dict, *, retriever: Retriever) -> dict:
    results: list[SearchResult] = retriever.retrieve(state["question"], top_k=5)
    return {"documents": results}
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/app/graph/nodes/test_retrieve.py -v
```
Expected: PASS 2개

- [ ] **Step 5: Commit**

```bash
git add app/graph/nodes/retrieve.py tests/app/graph/nodes/test_retrieve.py
git commit -m "feat(app): add retrieve_node using AgentState[question]"
```

---

### Task 4: app/graph/prompts.py + nodes/generate.py

**Files:**
- Create: `app/graph/prompts.py`
- Create: `app/graph/nodes/generate.py`
- Test: `tests/app/graph/nodes/test_generate.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/app/graph/nodes/test_generate.py`:
```python
from unittest.mock import MagicMock

from shared.models import Chunk, SearchResult
from app.graph.nodes.generate import generate_node


def _make_result(text: str, source: str) -> SearchResult:
    return SearchResult(chunk=Chunk(text=text, source=source), score=0.9)


def test_generate_node_returns_answer_and_citations():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "테스트 답변"

    state = {
        "question": "질문",
        "documents": [_make_result("문서 내용", "source.md")],
    }
    result = generate_node(state, llm=mock_llm)

    assert result["answer"] == "테스트 답변"
    assert result["citations"] == ["source.md"]


def test_generate_node_includes_context_in_prompt():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "답변"

    state = {
        "question": "질문",
        "documents": [_make_result("중요한 내용", "doc.md")],
    }
    generate_node(state, llm=mock_llm)

    called_prompt = mock_llm.complete.call_args[0][0]
    assert "중요한 내용" in called_prompt
    assert "질문" in called_prompt
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/app/graph/nodes/test_generate.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: prompts.py + generate_node 구현**

`app/graph/prompts.py`:
```python
RAG_GENERATE = "context:\n{context}\n\nquestion: {question}\nanswer in Korean."
```

`app/graph/nodes/generate.py`:
```python
from shared.llm.base import LLMClient
from app.graph.prompts import RAG_GENERATE


def generate_node(state: dict, *, llm: LLMClient) -> dict:
    question = state["question"]
    context = "\n\n".join(d.chunk.text for d in state["documents"])
    prompt = RAG_GENERATE.format(context=context, question=question)
    text = llm.complete(prompt)
    citations = [d.chunk.source for d in state["documents"]]
    return {"answer": text, "citations": citations}
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/app/graph/nodes/test_generate.py -v
```
Expected: PASS 2개

- [ ] **Step 5: Commit**

```bash
git add app/graph/prompts.py app/graph/nodes/generate.py tests/app/graph/nodes/test_generate.py
git commit -m "feat(app): add generate_node with extracted prompt template"
```

---

### Task 5: app/graph/edges.py (Phase 2 placeholder)

**Files:**
- Create: `app/graph/edges.py`

- [ ] **Step 1: edges.py 생성**

`app/graph/edges.py`:
```python
# Phase 2에서 조건부 분기 로직 추가 예정
# grade_documents 결과 기반 retry 분기, hallucination_check 기반 재생성 분기
```

- [ ] **Step 2: Commit**

```bash
git add app/graph/edges.py
git commit -m "chore(app): add edges.py placeholder for Phase 2 conditional routing"
```

---

### Task 6: app/graph/builder.py

**Files:**
- Create: `app/graph/builder.py`
- Test: `tests/app/graph/test_builder.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/app/graph/test_builder.py`:
```python
from unittest.mock import MagicMock

from shared.models import Answer, Chunk, SearchResult
from app.graph.builder import answer_question, build_graph


def _make_retriever(text: str = "문서", source: str = "doc.md"):
    mock = MagicMock()
    mock.retrieve.return_value = [
        SearchResult(chunk=Chunk(text=text, source=source), score=0.9)
    ]
    return mock


def test_build_graph_returns_compiled_graph():
    from langgraph.graph.state import CompiledStateGraph
    retriever = _make_retriever()
    llm = MagicMock()
    llm.complete.return_value = "답변"
    graph = build_graph(retriever=retriever, llm=llm)
    assert isinstance(graph, CompiledStateGraph)


def test_answer_question_returns_answer():
    retriever = _make_retriever(text="내용", source="s.md")
    llm = MagicMock()
    llm.complete.return_value = "정답"
    graph = build_graph(retriever=retriever, llm=llm)

    result = answer_question(graph, "테스트 질문")

    assert isinstance(result, Answer)
    assert result.text == "정답"
    assert result.sources == ["s.md"]
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/app/graph/test_builder.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: builder.py 구현**

`app/graph/builder.py`:
```python
from functools import partial

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from shared.llm.base import LLMClient
from shared.models import Answer
from shared.retriever.base import Retriever
from app.graph.nodes.generate import generate_node
from app.graph.nodes.retrieve import retrieve_node
from app.graph.state import AgentState


def build_graph(retriever: Retriever, llm: LLMClient) -> CompiledStateGraph:
    g = StateGraph(AgentState)
    g.add_node("retrieve", partial(retrieve_node, retriever=retriever))
    g.add_node("generate", partial(generate_node, llm=llm))
    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "generate")
    g.add_edge("generate", END)
    return g.compile()


def answer_question(graph: CompiledStateGraph, question: str) -> Answer:
    initial: AgentState = {
        "question": question,
        "rewritten_question": "",
        "chat_history": [],
        "route": "doc_search",
        "documents": [],
        "relevance_score": 0.0,
        "retry_count": 0,
        "answer": "",
        "citations": [],
        "hallucination_passed": False,
    }
    final = graph.invoke(initial)
    return Answer(text=final["answer"], sources=final["citations"])
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/app/graph/test_builder.py -v
```
Expected: PASS 2개

- [ ] **Step 5: Commit**

```bash
git add app/graph/builder.py tests/app/graph/test_builder.py
git commit -m "feat(app): add build_graph and answer_question in builder.py"
```

---

### Task 7: app/ingestion/ 모듈

**Files:**
- Create: `app/ingestion/chunker.py`, `app/ingestion/embedder.py`, `app/ingestion/indexer.py`
- Test: `tests/app/ingestion/test_ingestion.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/app/ingestion/test_ingestion.py`:
```python
def test_get_chunker_returns_chunker():
    from shared.chunker.base import Chunker
    from app.ingestion.chunker import get_chunker
    assert isinstance(get_chunker(), Chunker)


def test_get_embedder_returns_embedder():
    from shared.embedder.base import Embedder
    from app.ingestion.embedder import get_embedder
    assert isinstance(get_embedder("paraphrase-multilingual-MiniLM-L12-v2"), Embedder)


def test_build_index_function_exists():
    from app.ingestion.indexer import build_index
    import inspect
    assert inspect.isfunction(build_index)
    sig = inspect.signature(build_index)
    assert "docs_path" in sig.parameters
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/app/ingestion/test_ingestion.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: ingestion 모듈 구현**

`app/ingestion/chunker.py`:
```python
from shared.chunker import FixedSizeChunker
from shared.chunker.base import Chunker


def get_chunker(chunk_size: int = 500, overlap: int = 50) -> Chunker:
    return FixedSizeChunker(chunk_size=chunk_size, overlap=overlap)
```

`app/ingestion/embedder.py`:
```python
from shared.embedder import SentenceTransformerEmbedder
from shared.embedder.base import Embedder


def get_embedder(model: str) -> Embedder:
    return SentenceTransformerEmbedder(model)
```

`app/ingestion/indexer.py`:
```python
from shared.config import load_config
from shared.indexer.indexer import Indexer
from shared.loader import MarkdownLoader
from shared.vector_store.factory import create_vector_store
from app.ingestion.chunker import get_chunker
from app.ingestion.embedder import get_embedder


def build_index(docs_path: str) -> None:
    config = load_config()
    loader = MarkdownLoader(docs_path)
    chunker = get_chunker()
    embedder = get_embedder(config.embedding_model)
    store = create_vector_store(config)
    Indexer(loader=loader, chunker=chunker, embedder=embedder, store=store).index()
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/app/ingestion/test_ingestion.py -v
```
Expected: PASS 3개

- [ ] **Step 5: Commit**

```bash
git add app/ingestion/ tests/app/ingestion/
git commit -m "feat(app): add ingestion module (chunker, embedder, indexer)"
```

---

### Task 8: FastAPI 엔드포인트 + requirements.txt 갱신

**Files:**
- Modify: `requirements.txt`
- Create: `app/api/chat.py`
- Test: `tests/app/api/test_chat.py`

- [ ] **Step 1: requirements.txt에 FastAPI 추가**

`requirements.txt` 끝에 다음 두 줄 추가:
```
fastapi>=0.110.0
httpx>=0.27.0
```

- [ ] **Step 2: 실패 테스트 작성**

`tests/app/api/test_chat.py`:
```python
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from shared.models import Answer


def test_chat_returns_200():
    mock_answer = Answer(text="답변", sources=["doc.md"])
    with patch("app.api.chat.answer_question", return_value=mock_answer), \
         patch("app.api.chat.get_graph", return_value=MagicMock()):
        from app.api.chat import app
        client = TestClient(app)
        response = client.post("/chat", json={"question": "테스트"})
    assert response.status_code == 200


def test_chat_response_shape():
    mock_answer = Answer(text="답변 내용", sources=["a.md", "b.md"])
    with patch("app.api.chat.answer_question", return_value=mock_answer), \
         patch("app.api.chat.get_graph", return_value=MagicMock()):
        from app.api.chat import app
        client = TestClient(app)
        data = client.post("/chat", json={"question": "질문"}).json()
    assert data["answer"] == "답변 내용"
    assert data["sources"] == ["a.md", "b.md"]
```

- [ ] **Step 3: 패키지 설치**

```bash
pip install fastapi httpx
```

- [ ] **Step 4: 테스트 실패 확인**

```bash
pytest tests/app/api/test_chat.py -v
```
Expected: `ModuleNotFoundError: No module named 'app.api.chat'`

- [ ] **Step 5: chat.py 구현**

`app/api/chat.py`:
```python
from functools import lru_cache

from fastapi import FastAPI
from pydantic import BaseModel

from shared.config import load_config
from shared.embedder import SentenceTransformerEmbedder
from shared.llm.factory import create_llm
from shared.retriever import BasicRetriever
from shared.vector_store.factory import create_vector_store
from app.graph.builder import answer_question, build_graph

app = FastAPI()


class ChatRequest(BaseModel):
    question: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[str]


@lru_cache(maxsize=1)
def get_graph():
    config = load_config()
    embedder = SentenceTransformerEmbedder(config.embedding_model)
    store = create_vector_store(config)
    retriever = BasicRetriever(store=store, embedder=embedder)
    llm = create_llm(config)
    return build_graph(retriever=retriever, llm=llm)


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    result = answer_question(get_graph(), req.question)
    return ChatResponse(answer=result.text, sources=result.sources)
```

- [ ] **Step 6: 테스트 통과 확인**

```bash
pytest tests/app/api/test_chat.py -v
```
Expected: PASS 2개

- [ ] **Step 7: Commit**

```bash
git add requirements.txt app/api/chat.py tests/app/api/test_chat.py
git commit -m "feat(app): add FastAPI /chat endpoint"
```

---

### Task 9: scripts/ import 경로 업데이트

**Files:**
- Modify: `scripts/chat_rag_basic.py`, `scripts/build_index.py`, `scripts/eval_rag_basic.py`

- [ ] **Step 1: chat_rag_basic.py 수정**

`scripts/chat_rag_basic.py`에서 다음을 교체:
```python
# 변경 전
from graphs.rag_basic import answer_question, build_graph

# 변경 후
from app.graph.builder import answer_question, build_graph
```

- [ ] **Step 2: build_index.py 수정**

`scripts/build_index.py`에서 다음을 교체:
```python
# 변경 전
from shared.chunker import FixedSizeChunker
from shared.embedder import SentenceTransformerEmbedder
from shared.indexer.indexer import Indexer
from shared.loader import MarkdownLoader
from shared.observability.cache import CachedEmbedder, LRUCache
from shared.vector_store.factory import create_vector_store

# 변경 후 (main 함수 내 로직을 app.ingestion.indexer.build_index로 교체)
from app.ingestion.indexer import build_index
```

`scripts/build_index.py`의 `main()` 함수를:
```python
def main() -> None:
    docs_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs")
    build_index(docs_path)

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: eval_rag_basic.py 수정**

`scripts/eval_rag_basic.py`에서 다음을 교체:
```python
# 변경 전
from graphs.rag_basic import answer_question, build_graph
from eval_suite.runner import run_eval

# 변경 후
from app.graph.builder import answer_question, build_graph
from tests.eval.runner import run_eval
```

- [ ] **Step 4: dry-run 확인 (벡터 DB 없어도 import 오류만 없으면 됨)**

```bash
python -c "from scripts.chat_rag_basic import main; print('OK')"
python -c "from scripts.build_index import main; print('OK')"
python -c "from scripts.eval_rag_basic import main; print('OK')"
```
Expected: 각 `OK` 출력 (또는 DB 연결 오류 — import 오류는 없어야 함)

- [ ] **Step 5: Commit**

```bash
git add scripts/
git commit -m "chore(scripts): update imports from graphs/ to app/graph/"
```

---

### Task 10: eval_suite/ → tests/eval/ 이관

**Files:**
- Create: `tests/eval/__init__.py`, `tests/eval/runner.py`, `tests/eval/questions.yaml`
- Delete: `eval_suite/`

- [ ] **Step 1: tests/eval/ 생성 및 파일 복사**

```bash
mkdir -p tests/eval
cp eval_suite/runner.py tests/eval/runner.py
cp eval_suite/questions.yaml tests/eval/questions.yaml
touch tests/eval/__init__.py
```

- [ ] **Step 2: tests/eval/runner.py 내 경로 수정**

`tests/eval/runner.py`에서 기본 yaml 경로를 수정:
```python
# 변경 전
path = yaml_path or os.path.join(os.path.dirname(__file__), "questions.yaml")

# 변경 후 — 경로 그대로 동작 (os.path.dirname(__file__)이 tests/eval/를 가리킴)
# 변경 없음
```

- [ ] **Step 3: eval import 경로 확인**

```bash
python -c "from tests.eval.runner import run_eval; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: eval_suite/ 삭제**

```bash
rm -rf eval_suite/
```

- [ ] **Step 5: Commit**

```bash
git add tests/eval/
git rm -r eval_suite/
git commit -m "chore: migrate eval_suite/ to tests/eval/"
```

---

### Task 11: graphs/ 삭제 + CLAUDE.md ADR 갱신

**Files:**
- Delete: `graphs/`
- Modify: `CLAUDE.md`

- [ ] **Step 1: 전체 테스트 통과 확인 (삭제 전 최종 점검)**

```bash
pytest tests/ -v --ignore=tests/eval
```
Expected: 기존 테스트 전부 PASS (새 `tests/app/` 포함)

- [ ] **Step 2: graphs/ 삭제**

```bash
rm -rf graphs/
```

- [ ] **Step 3: 삭제 후 테스트 재확인**

```bash
pytest tests/ -v --ignore=tests/eval
```
Expected: 동일하게 PASS (graphs/에 의존하는 테스트 없어야 함)

- [ ] **Step 4: CLAUDE.md ADR 섹션 수정**

`CLAUDE.md`의 ADR 표에서 다음 행을 교체:

```markdown
<!-- 변경 전 -->
| 에이전트 시작점 | `create_agent` (Part 2-2) | `docs/langgraph-guide/03-agent.md` |
| RAG | 기본 워크플로우 (`graphs/rag_basic.py`) → 추후 고급 RAG | `docs/langgraph-guide/04-rag.md` |

<!-- 변경 후 -->
| 에이전트 시작점 | `create_agent` (Part 2-2) | `docs/langgraph-guide/03-agent.md` |
| RAG | `app/graph/` 워크플로우 슬라이스 (Phase 단위 확장) → `plan/plan.md` 기준 | `docs/langgraph-guide/04-rag.md` |
| State | `AgentState(TypedDict)` — plan.md §3 기준, MessagesState 미사용 | `app/graph/state.py` |
| 워크플로우 구조 | Phase 하나 = `app/graph/` 슬라이스. 신규 Phase는 nodes/ + edges.py 확장 | `plan/plan.md` |
```

- [ ] **Step 5: 최종 전체 테스트**

```bash
pytest tests/ -v --ignore=tests/eval
```
Expected: 전부 PASS

- [ ] **Step 6: Commit**

```bash
git rm -r graphs/
git add CLAUDE.md
git commit -m "chore: remove graphs/, update CLAUDE.md ADR to app/graph/ + AgentState"
```

---

## Self-Review 체크

- **Spec 커버리지**: ✅ app/graph/, app/ingestion/, app/api/, AgentState, plan.md 유지, CLAUDE.md 갱신 모두 포함
- **Placeholder 없음**: ✅ 모든 스텝에 실제 코드 포함
- **타입 일관성**: `AgentState` Task 2에서 정의 → Task 3/4에서 `state: dict` (런타임 TypedDict 호환), Task 6에서 `AgentState` 명시적 사용 ✅
- **누락 확인**: `langchain-anthropic` 패키지가 requirements.txt에 없으나 `create_chat_llm`이 Phase 1에서 미사용 → 문제 없음. Phase 3 도입 시 추가 필요.
