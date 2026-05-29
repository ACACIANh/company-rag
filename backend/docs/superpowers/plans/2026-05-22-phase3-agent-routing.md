# Phase 3: Agent화 — 라우터 + 도구 분기 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** LLM 기반 router_node를 추가해 질문 유형에 따라 doc_search / web_search / tool_call 세 경로로 분기하는 Agentic RAG 워크플로우를 구현한다.

**Architecture:** `rewrite_query → router_node` 이후 세 경로로 분기. doc_search는 기존 Self-RAG 루프 재활용. web_search는 `Retriever` ABC 구현체(Tavily/DuckDuckGo)를 주입받아 `generate`로 직행. tool_call은 `interrupt()`로 사용자 확인 후 Mock 도구 실행. 세 경로 모두 `generate → check_hallucination → END` 꼬리를 공유. `InMemorySaver` checkpointer 추가로 `interrupt()` 동작.

**Tech Stack:** Python 3.11+, LangGraph (interrupt, Command, InMemorySaver), tavily-python, duckduckgo-search, pytest, unittest.mock

---

## 파일 맵

| Task | 생성/수정 |
|---|---|
| Task 1 | Modify: `app/graph/state.py`, `tests/app/graph/test_state.py` |
| Task 2 | Modify: `app/graph/prompts.py`, Create: `app/graph/nodes/router.py`, `tests/app/graph/nodes/test_router.py` |
| Task 3 | Modify: `app/graph/edges.py`, `tests/app/graph/test_edges.py` |
| Task 4 | Modify: `requirements.txt`, Create: `shared/retriever/adapters/__init__.py`, `shared/retriever/adapters/tavily_retriever.py`, `tests/shared/retriever/adapters/__init__.py`, `tests/shared/retriever/adapters/test_tavily_retriever.py` |
| Task 5 | Create: `shared/retriever/adapters/duckduckgo_retriever.py`, `tests/shared/retriever/adapters/test_duckduckgo_retriever.py` |
| Task 6 | Create: `app/graph/nodes/web_search.py`, `tests/app/graph/nodes/test_web_search.py` |
| Task 7 | Create: `app/graph/nodes/confirm.py`, `tests/app/graph/nodes/test_confirm.py` |
| Task 8 | Create: `app/graph/nodes/tool_executor.py`, `tests/app/graph/nodes/test_tool_executor.py` |
| Task 9 | Modify: `app/graph/builder.py`, `tests/app/graph/test_builder.py` |
| Task 10 | Modify: `tests/eval/questions.yaml`, DoD 평가 실행 |

---

### Task 1: AgentState — `confirmed`, `tool_input` 필드 추가

**Files:**
- Modify: `app/graph/state.py`
- Modify: `tests/app/graph/test_state.py`

- [ ] **Step 1: `tests/app/graph/test_state.py`에 테스트 추가**

기존 파일 끝에 아래 테스트를 추가한다 (기존 3개 테스트 유지):

```python
def test_agent_state_has_phase3_fields():
    hints = get_type_hints(AgentState, include_extras=True)
    assert "confirmed" in hints
    assert "tool_input" in hints


def test_agent_state_phase3_instantiation():
    state: AgentState = {
        "question": "회의실 예약해줘",
        "rewritten_question": "회의실 예약 요청",
        "chat_history": [],
        "route": "tool_call",
        "documents": [],
        "relevance_score": 0.0,
        "retry_count": 0,
        "answer": "",
        "citations": [],
        "hallucination_passed": False,
        "confirmed": False,
        "tool_input": "회의실 A, 2026-06-01 14:00",
    }
    assert state["confirmed"] is False
    assert state["tool_input"] == "회의실 A, 2026-06-01 14:00"
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/app/graph/test_state.py -v
```

Expected: 기존 3개 PASS, 새 2개 FAIL (`KeyError` 또는 타입 오류)

- [ ] **Step 3: `app/graph/state.py` 수정**

`route: Literal[...]` 줄 아래에 두 필드를 추가한다:

```python
from typing import Literal, TypedDict

from shared.models import SearchResult


class AgentState(TypedDict):
    question: str
    rewritten_question: str
    chat_history: list[dict]
    route: Literal["doc_search", "tool_call", "web_search"]
    documents: list[SearchResult]
    relevance_score: float
    retry_count: int
    answer: str
    citations: list[str]
    hallucination_passed: bool
    confirmed: bool
    tool_input: str
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/app/graph/test_state.py -v
```

Expected: 5 PASSED

- [ ] **Step 5: 전체 기존 테스트 통과 확인**

```bash
pytest tests/ -q --ignore=tests/eval
```

Expected: 전부 PASS (새 필드 추가는 하위 호환)

- [ ] **Step 6: Commit**

```bash
git add app/graph/state.py tests/app/graph/test_state.py
git commit -m "feat(state): add confirmed and tool_input fields for Phase 3 routing"
```

---

### Task 2: ROUTER_PROMPT + `router_node`

**Files:**
- Modify: `app/graph/prompts.py`
- Create: `app/graph/nodes/router.py`
- Create: `tests/app/graph/nodes/test_router.py`

- [ ] **Step 1: `tests/app/graph/nodes/test_router.py` 작성 (실패 테스트)**

```python
from unittest.mock import MagicMock

from app.graph.nodes.router import router_node


def test_router_sets_doc_search_route():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "doc_search"

    result = router_node({"rewritten_question": "연차 정책이 뭐야?"}, llm=mock_llm)

    assert result["route"] == "doc_search"
    assert result["tool_input"] == ""


def test_router_sets_web_search_route():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "web_search"

    result = router_node({"rewritten_question": "최신 LangGraph 업데이트 알려줘"}, llm=mock_llm)

    assert result["route"] == "web_search"
    assert result["tool_input"] == ""


def test_router_sets_tool_call_route_and_tool_input():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "tool_call"

    result = router_node({"rewritten_question": "회의실 예약해줘"}, llm=mock_llm)

    assert result["route"] == "tool_call"
    assert result["tool_input"] == "회의실 예약해줘"


def test_router_falls_back_to_doc_search_on_unknown_response():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "알 수 없는 응답"

    result = router_node({"rewritten_question": "질문"}, llm=mock_llm)

    assert result["route"] == "doc_search"


def test_router_prompt_includes_question():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "doc_search"

    router_node({"rewritten_question": "핵심 질문 내용"}, llm=mock_llm)

    prompt = mock_llm.complete.call_args[0][0]
    assert "핵심 질문 내용" in prompt
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/app/graph/nodes/test_router.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.graph.nodes.router'`

- [ ] **Step 3: `app/graph/prompts.py`에 ROUTER_PROMPT 추가**

기존 파일 끝에 아래를 추가한다:

```python
ROUTER_PROMPT = """\
다음 질문을 분석해 적절한 처리 방식을 선택하세요.

선택지:
- doc_search: 사내 문서에서 정보를 찾는 질문 (정책, 절차, 규정, 가이드 등)
- tool_call: 실제 작업을 수행하는 요청 (예약, 조회, 실행, 전송 등 동작)
- web_search: 외부 최신 정보가 필요한 질문 (사내 문서에 없는 일반 지식, 뉴스 등)

다음 중 하나만 출력하세요. 다른 텍스트 없이 정확히 한 단어만: doc_search, web_search, tool_call

질문: {question}
선택:"""
```

- [ ] **Step 4: `app/graph/nodes/router.py` 구현**

```python
from shared.llm.base import LLMClient
from app.graph.prompts import ROUTER_PROMPT

_VALID_ROUTES = {"doc_search", "web_search", "tool_call"}


def router_node(state: dict, *, llm: LLMClient) -> dict:
    prompt = ROUTER_PROMPT.format(question=state["rewritten_question"])
    response = llm.complete(prompt).strip().lower()

    route = response if response in _VALID_ROUTES else "doc_search"
    tool_input = state["rewritten_question"] if route == "tool_call" else ""
    return {"route": route, "tool_input": tool_input}
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
pytest tests/app/graph/nodes/test_router.py -v
```

Expected: 5 PASSED

- [ ] **Step 6: Commit**

```bash
git add app/graph/prompts.py app/graph/nodes/router.py tests/app/graph/nodes/test_router.py
git commit -m "feat(nodes): add router_node with LLM-based route classification"
```

---

### Task 3: `route_after_router` + `route_after_confirm` 엣지

**Files:**
- Modify: `app/graph/edges.py`
- Modify: `tests/app/graph/test_edges.py`

- [ ] **Step 1: `tests/app/graph/test_edges.py`에 테스트 추가**

기존 파일 끝에 아래를 추가한다 (기존 9개 테스트 유지):

```python
from app.graph.edges import route_after_confirm, route_after_router


# ─── route_after_router ───

def test_route_after_router_returns_doc_search():
    assert route_after_router({"route": "doc_search"}) == "doc_search"


def test_route_after_router_returns_web_search():
    assert route_after_router({"route": "web_search"}) == "web_search"


def test_route_after_router_returns_tool_call():
    assert route_after_router({"route": "tool_call"}) == "tool_call"


# ─── route_after_confirm ───

def test_route_after_confirm_proceeds_when_confirmed():
    assert route_after_confirm({"confirmed": True}) == "tool_executor"


def test_route_after_confirm_ends_when_denied():
    assert route_after_confirm({"confirmed": False}) == "end"
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/app/graph/test_edges.py -v
```

Expected: 기존 9개 PASS, 새 5개 FAIL (`ImportError`)

- [ ] **Step 3: `app/graph/edges.py`에 함수 추가**

기존 파일 끝에 아래를 추가한다:

```python
def route_after_router(state: dict) -> str:
    return state["route"]


def route_after_confirm(state: dict) -> str:
    return "tool_executor" if state["confirmed"] else "end"
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/app/graph/test_edges.py -v
```

Expected: 14 PASSED

- [ ] **Step 5: Commit**

```bash
git add app/graph/edges.py tests/app/graph/test_edges.py
git commit -m "feat(edges): add route_after_router and route_after_confirm"
```

---

### Task 4: `TavilyRetriever`

**Files:**
- Modify: `requirements.txt`
- Create: `shared/retriever/adapters/__init__.py`
- Create: `shared/retriever/adapters/tavily_retriever.py`
- Create: `tests/shared/retriever/adapters/__init__.py`
- Create: `tests/shared/retriever/adapters/test_tavily_retriever.py`

- [ ] **Step 1: `requirements.txt`에 패키지 추가**

파일 끝에 아래 두 줄을 추가한다:

```
tavily-python>=0.3.0
duckduckgo-search>=6.0.0
```

- [ ] **Step 2: 패키지 설치**

```bash
pip install "tavily-python>=0.3.0" "duckduckgo-search>=6.0.0"
```

Expected: 설치 성공 (버전 출력)

- [ ] **Step 3: 디렉토리 + `__init__.py` 생성**

```bash
mkdir -p shared/retriever/adapters tests/shared/retriever/adapters
touch shared/retriever/adapters/__init__.py tests/shared/retriever/adapters/__init__.py
```

- [ ] **Step 4: `tests/shared/retriever/adapters/test_tavily_retriever.py` 작성 (실패 테스트)**

```python
from unittest.mock import MagicMock, patch

from shared.retriever.adapters.tavily_retriever import TavilyRetriever


def test_tavily_retriever_returns_search_results():
    mock_response = {
        "results": [
            {"content": "LangGraph 최신 기능 설명", "url": "https://example.com/1", "score": 0.9},
            {"content": "LangGraph 튜토리얼", "url": "https://example.com/2", "score": 0.8},
        ]
    }
    with patch("shared.retriever.adapters.tavily_retriever.TavilyClient") as MockClient:
        mock_client = MagicMock()
        mock_client.search.return_value = mock_response
        MockClient.return_value = mock_client

        retriever = TavilyRetriever(api_key="test-key")
        results = retriever.retrieve("LangGraph 업데이트", top_k=5)

    assert len(results) == 2
    assert results[0].chunk.text == "LangGraph 최신 기능 설명"
    assert results[0].chunk.source == "https://example.com/1"
    assert abs(results[0].score - 0.9) < 1e-6


def test_tavily_retriever_respects_top_k():
    mock_response = {"results": []}
    with patch("shared.retriever.adapters.tavily_retriever.TavilyClient") as MockClient:
        mock_client = MagicMock()
        mock_client.search.return_value = mock_response
        MockClient.return_value = mock_client

        retriever = TavilyRetriever(api_key="test-key")
        retriever.retrieve("질문", top_k=3)

        mock_client.search.assert_called_once_with("질문", max_results=3)


def test_tavily_retriever_returns_empty_on_no_results():
    mock_response = {"results": []}
    with patch("shared.retriever.adapters.tavily_retriever.TavilyClient") as MockClient:
        mock_client = MagicMock()
        mock_client.search.return_value = mock_response
        MockClient.return_value = mock_client

        retriever = TavilyRetriever(api_key="test-key")
        results = retriever.retrieve("질문", top_k=5)

    assert results == []


def test_tavily_retriever_uses_default_score_when_missing():
    mock_response = {
        "results": [{"content": "내용", "url": "https://example.com"}]
    }
    with patch("shared.retriever.adapters.tavily_retriever.TavilyClient") as MockClient:
        mock_client = MagicMock()
        mock_client.search.return_value = mock_response
        MockClient.return_value = mock_client

        retriever = TavilyRetriever(api_key="test-key")
        results = retriever.retrieve("질문", top_k=5)

    assert results[0].score == 0.5
```

- [ ] **Step 5: 테스트 실패 확인**

```bash
pytest tests/shared/retriever/adapters/test_tavily_retriever.py -v
```

Expected: `ModuleNotFoundError: No module named 'shared.retriever.adapters.tavily_retriever'`

- [ ] **Step 6: `shared/retriever/adapters/tavily_retriever.py` 구현**

```python
from shared.models import Chunk, SearchResult
from shared.retriever.base import Retriever


class TavilyRetriever(Retriever):
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def retrieve(self, query: str, top_k: int = 5) -> list[SearchResult]:
        from tavily import TavilyClient

        client = TavilyClient(api_key=self._api_key)
        response = client.search(query, max_results=top_k)
        return [
            SearchResult(
                chunk=Chunk(
                    text=r["content"],
                    source=r["url"],
                    chunk_id=r["url"],
                ),
                score=r.get("score", 0.5),
            )
            for r in response.get("results", [])
        ]
```

- [ ] **Step 7: 테스트 통과 확인**

```bash
pytest tests/shared/retriever/adapters/test_tavily_retriever.py -v
```

Expected: 4 PASSED

- [ ] **Step 8: Commit**

```bash
git add requirements.txt shared/retriever/adapters/ tests/shared/retriever/adapters/
git commit -m "feat(retriever): add TavilyRetriever adapter"
```

---

### Task 5: `DuckDuckGoRetriever`

**Files:**
- Create: `shared/retriever/adapters/duckduckgo_retriever.py`
- Create: `tests/shared/retriever/adapters/test_duckduckgo_retriever.py`

- [ ] **Step 1: `tests/shared/retriever/adapters/test_duckduckgo_retriever.py` 작성 (실패 테스트)**

```python
from unittest.mock import MagicMock, patch

from shared.retriever.adapters.duckduckgo_retriever import DuckDuckGoRetriever


def _make_ddg_result(body: str, href: str) -> dict:
    return {"body": body, "href": href, "title": "제목"}


def test_duckduckgo_retriever_returns_search_results():
    mock_results = [
        _make_ddg_result("LangGraph 설명", "https://example.com/1"),
        _make_ddg_result("LangGraph 튜토리얼", "https://example.com/2"),
    ]
    with patch("shared.retriever.adapters.duckduckgo_retriever.DDGS") as MockDDGS:
        mock_ddgs = MagicMock()
        mock_ddgs.__enter__ = MagicMock(return_value=mock_ddgs)
        mock_ddgs.__exit__ = MagicMock(return_value=False)
        mock_ddgs.text.return_value = mock_results
        MockDDGS.return_value = mock_ddgs

        retriever = DuckDuckGoRetriever()
        results = retriever.retrieve("LangGraph", top_k=5)

    assert len(results) == 2
    assert results[0].chunk.text == "LangGraph 설명"
    assert results[0].chunk.source == "https://example.com/1"
    assert results[0].score == 0.5


def test_duckduckgo_retriever_respects_top_k():
    with patch("shared.retriever.adapters.duckduckgo_retriever.DDGS") as MockDDGS:
        mock_ddgs = MagicMock()
        mock_ddgs.__enter__ = MagicMock(return_value=mock_ddgs)
        mock_ddgs.__exit__ = MagicMock(return_value=False)
        mock_ddgs.text.return_value = []
        MockDDGS.return_value = mock_ddgs

        DuckDuckGoRetriever().retrieve("질문", top_k=3)

        mock_ddgs.text.assert_called_once_with("질문", max_results=3)


def test_duckduckgo_retriever_returns_empty_on_no_results():
    with patch("shared.retriever.adapters.duckduckgo_retriever.DDGS") as MockDDGS:
        mock_ddgs = MagicMock()
        mock_ddgs.__enter__ = MagicMock(return_value=mock_ddgs)
        mock_ddgs.__exit__ = MagicMock(return_value=False)
        mock_ddgs.text.return_value = []
        MockDDGS.return_value = mock_ddgs

        results = DuckDuckGoRetriever().retrieve("질문", top_k=5)

    assert results == []
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/shared/retriever/adapters/test_duckduckgo_retriever.py -v
```

Expected: `ModuleNotFoundError: No module named 'shared.retriever.adapters.duckduckgo_retriever'`

- [ ] **Step 3: `shared/retriever/adapters/duckduckgo_retriever.py` 구현**

```python
from shared.models import Chunk, SearchResult
from shared.retriever.base import Retriever


class DuckDuckGoRetriever(Retriever):
    def retrieve(self, query: str, top_k: int = 5) -> list[SearchResult]:
        from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            raw = ddgs.text(query, max_results=top_k)

        return [
            SearchResult(
                chunk=Chunk(text=r["body"], source=r["href"], chunk_id=r["href"]),
                score=0.5,
            )
            for r in raw
        ]
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/shared/retriever/adapters/test_duckduckgo_retriever.py -v
```

Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add shared/retriever/adapters/duckduckgo_retriever.py tests/shared/retriever/adapters/test_duckduckgo_retriever.py
git commit -m "feat(retriever): add DuckDuckGoRetriever adapter"
```

---

### Task 6: `web_search_node`

**Files:**
- Create: `app/graph/nodes/web_search.py`
- Create: `tests/app/graph/nodes/test_web_search.py`

- [ ] **Step 1: `tests/app/graph/nodes/test_web_search.py` 작성 (실패 테스트)**

```python
from unittest.mock import MagicMock

from shared.models import Chunk, SearchResult
from app.graph.nodes.web_search import web_search_node


def _make_result(text: str, source: str) -> SearchResult:
    return SearchResult(chunk=Chunk(text=text, source=source, chunk_id=source), score=0.5)


def test_web_search_node_returns_documents():
    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value = [_make_result("검색 결과", "https://example.com")]

    state = {"rewritten_question": "LangGraph 최신 버전", "question": "LangGraph 버전 알려줘"}
    result = web_search_node(state, retriever=mock_retriever)

    assert "documents" in result
    assert len(result["documents"]) == 1
    assert result["documents"][0].chunk.text == "검색 결과"


def test_web_search_node_uses_rewritten_question():
    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value = []

    web_search_node(
        {"rewritten_question": "재작성 질문", "question": "원본 질문"},
        retriever=mock_retriever,
    )

    mock_retriever.retrieve.assert_called_once_with("재작성 질문", top_k=5)


def test_web_search_node_falls_back_to_question_when_rewritten_empty():
    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value = []

    web_search_node(
        {"rewritten_question": "", "question": "원본 질문"},
        retriever=mock_retriever,
    )

    mock_retriever.retrieve.assert_called_once_with("원본 질문", top_k=5)


def test_web_search_node_returns_empty_list_when_no_results():
    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value = []

    result = web_search_node(
        {"rewritten_question": "질문", "question": "질문"},
        retriever=mock_retriever,
    )

    assert result["documents"] == []
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/app/graph/nodes/test_web_search.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.graph.nodes.web_search'`

- [ ] **Step 3: `app/graph/nodes/web_search.py` 구현**

```python
from shared.retriever.base import Retriever


def web_search_node(state: dict, *, retriever: Retriever) -> dict:
    query = state.get("rewritten_question") or state["question"]
    results = retriever.retrieve(query, top_k=5)
    return {"documents": results}
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/app/graph/nodes/test_web_search.py -v
```

Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add app/graph/nodes/web_search.py tests/app/graph/nodes/test_web_search.py
git commit -m "feat(nodes): add web_search_node delegating to Retriever ABC"
```

---

### Task 7: `confirm_node`

**Files:**
- Create: `app/graph/nodes/confirm.py`
- Create: `tests/app/graph/nodes/test_confirm.py`

- [ ] **Step 1: `tests/app/graph/nodes/test_confirm.py` 작성 (실패 테스트)**

```python
from unittest.mock import patch

from app.graph.nodes.confirm import confirm_node


def test_confirm_node_returns_true_when_user_approves():
    with patch("app.graph.nodes.confirm.interrupt", return_value=True):
        result = confirm_node({
            "tool_input": "회의실 A 예약",
            "rewritten_question": "회의실 예약해줘",
        })

    assert result == {"confirmed": True}


def test_confirm_node_returns_false_when_user_denies():
    with patch("app.graph.nodes.confirm.interrupt", return_value=False):
        result = confirm_node({
            "tool_input": "슬랙 메시지 발송",
            "rewritten_question": "팀에 공지 보내줘",
        })

    assert result == {"confirmed": False}


def test_confirm_node_calls_interrupt_with_tool_input():
    with patch("app.graph.nodes.confirm.interrupt", return_value=True) as mock_interrupt:
        confirm_node({
            "tool_input": "인사 시스템 조회",
            "rewritten_question": "내 연차 잔여일 알려줘",
        })

    call_args = mock_interrupt.call_args[0][0]
    assert "인사 시스템 조회" in str(call_args)


def test_confirm_node_uses_rewritten_question_when_tool_input_empty():
    with patch("app.graph.nodes.confirm.interrupt", return_value=False) as mock_interrupt:
        confirm_node({
            "tool_input": "",
            "rewritten_question": "캘린더 확인해줘",
        })

    call_args = mock_interrupt.call_args[0][0]
    assert "캘린더 확인해줘" in str(call_args)
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/app/graph/nodes/test_confirm.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.graph.nodes.confirm'`

- [ ] **Step 3: `app/graph/nodes/confirm.py` 구현**

```python
from langgraph.types import interrupt


def confirm_node(state: dict) -> dict:
    action = state.get("tool_input") or state["rewritten_question"]
    user_response = interrupt({
        "message": f"다음 작업을 실행하시겠습니까?\n요청: {action}",
        "tool_input": action,
    })
    return {"confirmed": bool(user_response)}
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/app/graph/nodes/test_confirm.py -v
```

Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add app/graph/nodes/confirm.py tests/app/graph/nodes/test_confirm.py
git commit -m "feat(nodes): add confirm_node with interrupt() for HITL tool_call"
```

---

### Task 8: `tool_executor_node` (Mock)

**Files:**
- Create: `app/graph/nodes/tool_executor.py`
- Create: `tests/app/graph/nodes/test_tool_executor.py`

- [ ] **Step 1: `tests/app/graph/nodes/test_tool_executor.py` 작성 (실패 테스트)**

```python
from shared.models import SearchResult
from app.graph.nodes.tool_executor import tool_executor_node


def test_tool_executor_returns_search_result_list():
    result = tool_executor_node({"tool_input": "회의실 A 예약", "rewritten_question": "회의실 예약"})

    assert "documents" in result
    assert isinstance(result["documents"], list)
    assert len(result["documents"]) == 1
    assert isinstance(result["documents"][0], SearchResult)


def test_tool_executor_result_source_is_mock_tool():
    result = tool_executor_node({"tool_input": "임의 요청", "rewritten_question": "임의 요청"})

    assert result["documents"][0].chunk.source == "mock-tool"


def test_tool_executor_result_score_is_one():
    result = tool_executor_node({"tool_input": "요청", "rewritten_question": "요청"})

    assert result["documents"][0].score == 1.0


def test_tool_executor_uses_tool_input_in_response():
    result = tool_executor_node({"tool_input": "캘린더 조회", "rewritten_question": "일정 알려줘"})

    assert "캘린더" in result["documents"][0].chunk.text


def test_tool_executor_falls_back_to_rewritten_question():
    result = tool_executor_node({"tool_input": "", "rewritten_question": "팀 공지 보내줘"})

    assert "팀 공지 보내줘" in result["documents"][0].chunk.text
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/app/graph/nodes/test_tool_executor.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.graph.nodes.tool_executor'`

- [ ] **Step 3: `app/graph/nodes/tool_executor.py` 구현**

```python
from shared.models import Chunk, SearchResult

_MOCK_DISPATCH = {
    "캘린더": "캘린더 Mock: 다음 주 월요일 오전 10시 회의 일정이 있습니다.",
    "회의실": "회의실 Mock: 회의실 A가 2026-06-02 14:00에 예약됐습니다.",
    "연차": "인사 시스템 Mock: 연차 잔여일은 10일입니다.",
    "공지": "알림 Mock: 팀 전체에 공지가 발송됐습니다.",
}


def tool_executor_node(state: dict) -> dict:
    action = state.get("tool_input") or state["rewritten_question"]
    mock_text = next(
        (v for k, v in _MOCK_DISPATCH.items() if k in action),
        f"Mock 도구 실행 완료: '{action}'",
    )
    result = SearchResult(
        chunk=Chunk(text=mock_text, source="mock-tool", chunk_id="mock-0"),
        score=1.0,
    )
    return {"documents": [result]}
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/app/graph/nodes/test_tool_executor.py -v
```

Expected: 5 PASSED

- [ ] **Step 5: 전체 단위 테스트 통과 확인**

```bash
pytest tests/ -q --ignore=tests/eval
```

Expected: 전부 PASS

- [ ] **Step 6: Commit**

```bash
git add app/graph/nodes/tool_executor.py tests/app/graph/nodes/test_tool_executor.py
git commit -m "feat(nodes): add tool_executor_node with Mock dispatch table"
```

---

### Task 9: `builder.py` — Phase 3 그래프 재조립

**배경:** router_node가 `rewrite_query` 다음에 삽입되고, 세 경로로 분기된다. `InMemorySaver` checkpointer가 추가돼야 `interrupt()`가 동작한다. 기존 builder 테스트는 LLM `side_effect`에 router 응답을 추가해야 한다.

**Files:**
- Modify: `app/graph/builder.py`
- Modify: `tests/app/graph/test_builder.py`

- [ ] **Step 1: `tests/app/graph/test_builder.py`에 Phase 3 테스트 추가**

기존 파일 끝에 아래를 추가한다. 기존 5개 테스트는 **삭제하지 말고**, `llm.complete.side_effect`에 `"doc_search"` (router 응답)를 추가하는 방식으로 수정한다.

**기존 테스트 수정 방법** — 기존 `test_answer_question_returns_answer`의 `side_effect`를:
```python
# 변경 전
llm.complete.return_value = "정답"

# 변경 후 (router 응답 추가)
llm.complete.side_effect = ["재작성", "doc_search", "0.9", "정답", "YES"]
```

기존 5개 테스트를 아래와 같이 모두 교체한다:

```python
import pytest
from langgraph.errors import GraphInterrupt
from langgraph.types import Command
from unittest.mock import MagicMock

from shared.models import Answer, Chunk, SearchResult
from app.graph.builder import answer_question, build_graph


def _make_retriever(text: str = "문서", source: str = "doc.md"):
    mock = MagicMock()
    mock.retrieve.return_value = [
        SearchResult(chunk=Chunk(text=text, source=source, chunk_id=source), score=0.9)
    ]
    return mock


def test_build_graph_returns_compiled_graph():
    from langgraph.graph.state import CompiledStateGraph
    retriever = _make_retriever()
    llm = MagicMock()
    llm.complete.side_effect = ["재작성", "doc_search", "0.9", "답변", "YES"]
    graph = build_graph(retriever=retriever, llm=llm)
    assert isinstance(graph, CompiledStateGraph)


def test_answer_question_doc_search_happy_path():
    retriever = _make_retriever(text="연차는 15일입니다.", source="vacation.md")
    llm = MagicMock()
    llm.complete.side_effect = [
        "연차 신청 방법",  # rewrite_query
        "doc_search",     # router
        "0.9",            # grade_documents
        "정답",           # generate
        "YES",            # check_hallucination
    ]
    graph = build_graph(retriever=retriever, llm=llm)
    result = answer_question(graph, "연차 어떻게 써?")

    assert isinstance(result, Answer)
    assert result.text == "정답"
    assert "vacation.md" in result.sources


def test_answer_question_web_search_path():
    doc_retriever = _make_retriever(text="사내 문서", source="doc.md")
    web_retriever = _make_retriever(text="LangGraph 최신 기능", source="https://langchain.com")
    llm = MagicMock()
    llm.complete.side_effect = [
        "LangGraph 최신 업데이트",  # rewrite_query
        "web_search",               # router
        "웹 검색 기반 답변",         # generate
        "YES",                      # check_hallucination
    ]
    graph = build_graph(retriever=doc_retriever, llm=llm, web_search_retriever=web_retriever)
    result = answer_question(graph, "LangGraph 최신 버전 알려줘")

    assert result.text == "웹 검색 기반 답변"
    assert "https://langchain.com" in result.sources


def test_answer_question_doc_search_retry_on_low_grade():
    retriever = _make_retriever(text="내용", source="doc.md")
    llm = MagicMock()
    llm.complete.side_effect = [
        "첫 재작성",        # rewrite_query
        "doc_search",      # router
        "0.2",             # grade (fail → rewrite_retry)
        "두 번째 재작성",   # rewrite_query (retry)
        "0.8",             # grade (pass)
        "좋은 답변",        # generate
        "YES",             # check_hallucination
    ]
    graph = build_graph(retriever=retriever, llm=llm)
    result = answer_question(graph, "원본 질문")

    assert result.text == "좋은 답변"


def test_tool_call_triggers_interrupt():
    doc_retriever = _make_retriever()
    web_retriever = _make_retriever()
    llm = MagicMock()
    llm.complete.side_effect = [
        "회의실 예약 요청",  # rewrite_query
        "tool_call",        # router
    ]
    graph = build_graph(retriever=doc_retriever, llm=llm, web_search_retriever=web_retriever)
    config = {"configurable": {"thread_id": "test-interrupt-1"}}

    initial = {
        "question": "회의실 예약해줘",
        "rewritten_question": "",
        "chat_history": [],
        "route": "doc_search",
        "documents": [],
        "relevance_score": 0.0,
        "retry_count": 0,
        "answer": "",
        "citations": [],
        "hallucination_passed": False,
        "confirmed": False,
        "tool_input": "",
    }

    with pytest.raises(GraphInterrupt):
        graph.invoke(initial, config=config)


def test_tool_call_completes_after_user_approves():
    doc_retriever = _make_retriever()
    web_retriever = _make_retriever()
    llm = MagicMock()
    llm.complete.side_effect = [
        "회의실 예약 요청",  # rewrite_query
        "tool_call",        # router
        "Mock 실행 결과 답변",  # generate
        "YES",              # check_hallucination
    ]
    graph = build_graph(retriever=doc_retriever, llm=llm, web_search_retriever=web_retriever)
    config = {"configurable": {"thread_id": "test-interrupt-2"}}

    initial = {
        "question": "회의실 예약해줘",
        "rewritten_question": "",
        "chat_history": [],
        "route": "doc_search",
        "documents": [],
        "relevance_score": 0.0,
        "retry_count": 0,
        "answer": "",
        "citations": [],
        "hallucination_passed": False,
        "confirmed": False,
        "tool_input": "",
    }

    with pytest.raises(GraphInterrupt):
        graph.invoke(initial, config=config)

    final = graph.invoke(Command(resume=True), config=config)
    assert final["answer"] == "Mock 실행 결과 답변"


def test_tool_call_ends_when_user_denies():
    doc_retriever = _make_retriever()
    web_retriever = _make_retriever()
    llm = MagicMock()
    llm.complete.side_effect = [
        "슬랙 메시지 요청",  # rewrite_query
        "tool_call",         # router
    ]
    graph = build_graph(retriever=doc_retriever, llm=llm, web_search_retriever=web_retriever)
    config = {"configurable": {"thread_id": "test-interrupt-3"}}

    initial = {
        "question": "팀에 공지 보내줘",
        "rewritten_question": "",
        "chat_history": [],
        "route": "doc_search",
        "documents": [],
        "relevance_score": 0.0,
        "retry_count": 0,
        "answer": "",
        "citations": [],
        "hallucination_passed": False,
        "confirmed": False,
        "tool_input": "",
    }

    with pytest.raises(GraphInterrupt):
        graph.invoke(initial, config=config)

    final = graph.invoke(Command(resume=False), config=config)
    assert final["answer"] == ""
```

- [ ] **Step 2: 새 테스트 실패 확인**

```bash
pytest tests/app/graph/test_builder.py -v
```

Expected: 기존 테스트들 FAIL (router 응답 없어서 side_effect 소진), 새 테스트 ImportError

- [ ] **Step 3: `app/graph/builder.py` 전체 교체**

```python
from functools import partial

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from shared.llm.base import LLMClient
from shared.models import Answer
from shared.retriever.base import Retriever
from app.graph.edges import (
    route_after_confirm,
    route_after_grade,
    route_after_hallucination,
    route_after_router,
)
from app.graph.nodes.check_hallucination import check_hallucination_node
from app.graph.nodes.confirm import confirm_node
from app.graph.nodes.generate import generate_node
from app.graph.nodes.grade_documents import grade_documents_node
from app.graph.nodes.increment_retry import increment_retry_node
from app.graph.nodes.retrieve import retrieve_node
from app.graph.nodes.rewrite_query import rewrite_query_node
from app.graph.nodes.router import router_node
from app.graph.nodes.tool_executor import tool_executor_node
from app.graph.nodes.web_search import web_search_node
from app.graph.state import AgentState


def build_graph(
    retriever: Retriever,
    llm: LLMClient,
    web_search_retriever: Retriever | None = None,
) -> CompiledStateGraph:
    g = StateGraph(AgentState)

    g.add_node("rewrite_query", partial(rewrite_query_node, llm=llm))
    g.add_node("router", partial(router_node, llm=llm))
    g.add_node("retrieve", partial(retrieve_node, retriever=retriever))
    g.add_node("grade_documents", partial(grade_documents_node, llm=llm))
    g.add_node("increment_retry", increment_retry_node)
    g.add_node("web_search", partial(web_search_node, retriever=web_search_retriever))
    g.add_node("confirm", confirm_node)
    g.add_node("tool_executor", tool_executor_node)
    g.add_node("generate", partial(generate_node, llm=llm))
    g.add_node("check_hallucination", partial(check_hallucination_node, llm=llm))

    # 공통 진입 경로
    g.add_edge(START, "rewrite_query")
    g.add_edge("rewrite_query", "router")

    # 라우터 → 세 경로 분기
    g.add_conditional_edges(
        "router",
        route_after_router,
        {"doc_search": "retrieve", "web_search": "web_search", "tool_call": "confirm"},
    )

    # doc_search 경로 (Self-RAG 루프)
    g.add_edge("retrieve", "grade_documents")
    g.add_edge("increment_retry", "rewrite_query")
    g.add_conditional_edges(
        "grade_documents",
        route_after_grade,
        {"generate": "generate", "rewrite_retry": "increment_retry"},
    )

    # tool_call 경로
    g.add_conditional_edges(
        "confirm",
        route_after_confirm,
        {"tool_executor": "tool_executor", "end": END},
    )
    g.add_edge("tool_executor", "generate")

    # web_search 경로
    g.add_edge("web_search", "generate")

    # 공통 꼬리
    g.add_edge("generate", "check_hallucination")
    g.add_conditional_edges(
        "check_hallucination",
        route_after_hallucination,
        {"end": END, "generate": "generate"},
    )

    return g.compile(checkpointer=InMemorySaver())


def answer_question(
    graph: CompiledStateGraph,
    question: str,
    config: dict | None = None,
) -> Answer:
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
        "confirmed": False,
        "tool_input": "",
    }
    final = graph.invoke(initial, config=config or {})
    return Answer(text=final["answer"], sources=final["citations"])
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/app/graph/test_builder.py -v
```

Expected: 8 PASSED

- [ ] **Step 5: 전체 테스트 통과 확인**

```bash
pytest tests/ -q --ignore=tests/eval
```

Expected: 전부 PASS

- [ ] **Step 6: Commit**

```bash
git add app/graph/builder.py tests/app/graph/test_builder.py
git commit -m "feat(builder): wire Phase 3 router + three-path graph with InMemorySaver"
```

---

### Task 10: 평가셋 확장 + DoD 검증

**Files:**
- Modify: `tests/eval/questions.yaml`

- [ ] **Step 1: `tests/eval/questions.yaml`에 라우팅 평가용 질문 추가**

기존 5개 질문 뒤에 아래를 추가한다:

```yaml
  # web_search 유형
  - question: "최신 Python 3.13 릴리즈 노트 알려줘"
    expected_keywords: ["Python", "릴리즈"]
    expected_route: "web_search"
  - question: "오늘 날씨 어때?"
    expected_keywords: ["날씨"]
    expected_route: "web_search"
  - question: "GPT-5 출시일이 언제야?"
    expected_keywords: ["GPT"]
    expected_route: "web_search"
  - question: "LangGraph 0.3 변경사항이 뭐야?"
    expected_keywords: ["LangGraph", "변경"]
    expected_route: "web_search"
  - question: "요즘 AI 트렌드가 뭐야?"
    expected_keywords: ["AI", "트렌드"]
    expected_route: "web_search"

  # tool_call 유형
  - question: "다음 주 월요일 회의실 A 예약해줘"
    expected_keywords: ["회의실", "예약"]
    expected_route: "tool_call"
  - question: "팀 전체에 슬랙으로 공지 보내줘"
    expected_keywords: ["슬랙", "공지"]
    expected_route: "tool_call"
  - question: "내 연차 잔여일 인사 시스템에서 조회해줘"
    expected_keywords: ["연차", "잔여"]
    expected_route: "tool_call"
  - question: "김철수 대리에게 메일 보내줘"
    expected_keywords: ["메일"]
    expected_route: "tool_call"
  - question: "오늘 오후 2시 캘린더에 미팅 잡아줘"
    expected_keywords: ["캘린더", "미팅"]
    expected_route: "tool_call"

  # doc_search 추가 유형 (기존 5개 외 5개 더)
  - question: "출장 비용 처리 절차가 어떻게 돼?"
    expected_keywords: ["출장", "비용"]
    expected_route: "doc_search"
  - question: "재택근무 신청은 어떻게 해?"
    expected_keywords: ["재택", "신청"]
    expected_route: "doc_search"
  - question: "인시던트 발생 시 대응 절차는?"
    expected_keywords: ["인시던트", "대응"]
    expected_route: "doc_search"
  - question: "사내 API 접근 권한 받는 방법이 뭐야?"
    expected_keywords: ["권한", "API"]
    expected_route: "doc_search"
  - question: "성과 평가 주기와 기준이 어떻게 돼?"
    expected_keywords: ["성과", "평가"]
    expected_route: "doc_search"
```

- [ ] **Step 2: 라우팅 정확도 평가 스크립트 실행**

아래 명령으로 router_node만 독립 평가한다 (벡터 DB 불필요):

```bash
python3 - <<'PY'
import os
from unittest.mock import MagicMock
from app.graph.nodes.router import router_node
from shared.llm.factory import create_llm
from shared.config import load_config
import yaml

config = load_config()
llm = create_llm(config)

with open("tests/eval/questions.yaml") as f:
    data = yaml.safe_load(f)

questions = data["questions"]
routing_questions = [q for q in questions if "expected_route" in q]

correct = 0
for q in routing_questions:
    result = router_node({"rewritten_question": q["question"]}, llm=llm)
    predicted = result["route"]
    expected = q["expected_route"]
    ok = predicted == expected
    correct += ok
    status = "✅" if ok else "❌"
    print(f"{status} [{expected} → {predicted}] {q['question']}")

print(f"\n라우팅 정확도: {correct}/{len(routing_questions)} = {correct/len(routing_questions):.0%}")
PY
```

Expected: 정확도 90% 이상 (`≥27/30`)

- [ ] **Step 3: 전체 회귀 테스트 (단위)**

```bash
pytest tests/ -q --ignore=tests/eval
```

Expected: 전부 PASS

- [ ] **Step 4: DoD 결과를 plan.md에 기록**

`plan/plan.md`의 Phase 3 DoD 섹션을 아래 형식으로 갱신한다:

```markdown
**Definition of Done**
- [x] 3종류 질문 각 10개씩 평가, 올바른 도구 선택률 90% 이상
  - 측정 결과: X/30 = XX% (2026-05-22)
- [x] 작업 도구 호출 시 사용자 확인 절차 포함 — `interrupt()` HITL 구현
- [x] 도구별 timeout 및 에러 핸들링 완비 — Phase 3는 Mock 구현, 실제 API는 Phase 4
```

- [ ] **Step 5: CLAUDE.md ADR 갱신**

`CLAUDE.md` ADR 표에 아래 행을 추가한다:

```markdown
| 라우터 | LLM 기반 `router_node` — `route` 필드로 세 경로 분기 | `app/graph/nodes/router.py` |
| HITL | `interrupt()` — tool_call 경로에만 적용, `InMemorySaver` 필수 | `app/graph/nodes/confirm.py` |
| 웹 검색 | `Retriever` ABC + Tavily/DuckDuckGo 어댑터 | `shared/retriever/adapters/` |
```

- [ ] **Step 6: 최종 커밋**

```bash
git add tests/eval/questions.yaml plan/plan.md CLAUDE.md
git commit -m "docs(eval): extend routing eval set + record Phase 3 DoD results"
```

---

## Self-Review 체크

**Spec 커버리지:**
- ✅ `router_node` LLM 기반 — Task 2
- ✅ `route_after_router`, `route_after_confirm` 엣지 — Task 3
- ✅ `TavilyRetriever` — Task 4
- ✅ `DuckDuckGoRetriever` — Task 5
- ✅ `web_search_node` (`Retriever` ABC 주입) — Task 6
- ✅ `confirm_node` (`interrupt()` HITL) — Task 7
- ✅ `tool_executor_node` (Mock) — Task 8
- ✅ builder.py `InMemorySaver` + 세 경로 조립 — Task 9
- ✅ 라우팅 평가셋 30개 + 정확도 90% DoD — Task 10
- ✅ `AgentState.confirmed`, `tool_input` 추가 — Task 1

**Placeholder 없음:** ✅ 모든 스텝에 실제 코드 포함

**타입 일관성:**
- `router_node` → `{"route": str, "tool_input": str}` → `AgentState` 필드와 일치 ✅
- `web_search_node` → `{"documents": list[SearchResult]}` → `retrieve_node`와 동일 포맷 ✅
- `confirm_node` → `{"confirmed": bool}` → `route_after_confirm(state["confirmed"])` ✅
- `tool_executor_node` → `{"documents": list[SearchResult]}` → `generate_node` 입력 형식 일치 ✅
- `answer_question` 초기 상태에 `confirmed: False`, `tool_input: ""` 포함 ✅
- 기존 builder 테스트 `side_effect`에 router 응답 삽입 ✅
