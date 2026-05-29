# Multi-Query Rewriting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 멀티턴 RAG의 검색 품질 개선을 위해 Router가 `rewrite_strategy`를 결정하고, `multi_query` 전략 시 하위 쿼리 N개로 분해 후 RRF 병합 검색을 수행한다.

**Architecture:** 기존 `rewrite_query → router` 흐름을 유지하면서 Router 출력에 `rewrite_strategy` 필드를 추가한다. 전략이 `multi_query`이면 `multi_query` 노드를 경유해 하위 쿼리를 생성하고, `retrieve_node`에서 asyncio.gather로 병렬 검색 후 RRF merge한다.

**Tech Stack:** Python 3.11+, LangGraph, `shared.llm.base.LLMClient`, `shared.models.SearchResult`, asyncio

---

## 파일 구조 (변경 대상)

| 작업 | 파일 | 변경 유형 |
|------|------|-----------|
| Task 1 | `app/graph/state.py` | Modify — `rewrite_strategy`, `multi_queries` 필드 추가 |
| Task 2 | `app/graph/prompts.py` | Modify — `ROUTER_PROMPT` 교체, `MULTI_QUERY_PROMPT` 추가 |
| Task 3 | `app/graph/nodes/router.py` | Modify — `rewrite_strategy` 출력 추가 |
| Task 4 | `app/graph/nodes/multi_query.py` | Create — 하위 쿼리 확장 노드 |
| Task 5 | `app/graph/nodes/retrieve.py` | Modify — multi-query 병렬 검색 + RRF merge |
| Task 6 | `app/graph/edges.py` | Modify — `route_after_router` 에서 `multi_query` 분기 추가 |
| Task 7 | `app/graph/builder.py` | Modify — `multi_query` 노드 등록, conditional edges 갱신, 초기 state 갱신 |
| Test A | `tests/app/graph/nodes/test_router.py` | Modify — `rewrite_strategy` 반환값 검증 테스트 추가 |
| Test B | `tests/app/graph/nodes/test_multi_query.py` | Create — multi_query_node 단위 테스트 |
| Test C | `tests/app/graph/nodes/test_retrieve.py` | Modify — multi-query 경로 테스트 추가 |
| Test D | `tests/app/graph/test_edges.py` | Modify — `route_after_router` multi_query 분기 테스트 추가 |
| Test E | `tests/app/graph/test_state.py` | Modify — 새 필드 검증 추가 |

---

## Task 1: AgentState 확장

**Files:**
- Modify: `app/graph/state.py`
- Test: `tests/app/graph/test_state.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/app/graph/test_state.py` 에 다음을 추가:

```python
def test_agent_state_has_multi_query_fields():
    hints = get_type_hints(AgentState, include_extras=True)
    assert "rewrite_strategy" in hints
    assert "multi_queries" in hints


def test_agent_state_multi_query_instantiation():
    state: AgentState = {
        "question": "연차 vs 병가 비교",
        "rewritten_question": "연차와 병가의 차이점은?",
        "chat_history": [],
        "route": "doc_search",
        "rewrite_strategy": "multi_query",
        "multi_queries": ["연차 규정은?", "병가 규정은?"],
        "documents": [],
        "relevance_score": 0.0,
        "retry_count": 0,
        "answer": "",
        "citations": [],
        "hallucination_passed": False,
        "confirmed": False,
        "tool_input": "",
        "user_id": "u1",
        "allowed_doc_ids": [],
        "user_teams": [],
        "personal_doc_ids": [],
    }
    assert state["rewrite_strategy"] == "multi_query"
    assert state["multi_queries"] == ["연차 규정은?", "병가 규정은?"]
```

- [ ] **Step 2: 테스트 실행 → FAIL 확인**

```bash
cd /Users/acacian/vscode/company-rag
pytest tests/app/graph/test_state.py::test_agent_state_has_multi_query_fields -v
```

Expected: `FAILED — KeyError: 'rewrite_strategy'`

- [ ] **Step 3: AgentState에 필드 추가**

`app/graph/state.py` 전체를 다음으로 교체:

```python
from typing import Literal, TypedDict

from shared.models import SearchResult, SourceRef


class AgentState(TypedDict):
    question: str
    rewritten_question: str
    chat_history: list[dict]
    route: Literal["doc_search", "tool_call", "web_search"]
    rewrite_strategy: Literal["none", "contextual", "multi_query"] | None
    multi_queries: list[str]
    documents: list[SearchResult]
    relevance_score: float
    retry_count: int
    answer: str
    citations: list[SourceRef]
    hallucination_passed: bool
    confirmed: bool
    tool_input: str
    user_id: str
    allowed_doc_ids: list[str]   # deprecated — FGA 미연동 테스트 stub용
    user_teams: list[str]        # permission_node가 채움
    personal_doc_ids: list[str]  # permission_node가 채움
```

- [ ] **Step 4: 테스트 실행 → PASS 확인**

```bash
pytest tests/app/graph/test_state.py -v
```

Expected: `4 passed` (기존 4개 + 신규 2개 = 6개, 모두 PASS)

- [ ] **Step 5: 커밋**

```bash
git add app/graph/state.py tests/app/graph/test_state.py
git commit -m "feat(state): AgentState에 rewrite_strategy, multi_queries 필드 추가"
```

---

## Task 2: 프롬프트 업데이트

**Files:**
- Modify: `app/graph/prompts.py`

- [ ] **Step 1: ROUTER_PROMPT 교체 + MULTI_QUERY_PROMPT 추가**

`app/graph/prompts.py`의 `ROUTER_PROMPT` 블록을 다음으로 교체하고, 파일 끝에 `MULTI_QUERY_PROMPT`를 추가:

기존 `ROUTER_PROMPT`:
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

교체할 내용:
```python
ROUTER_PROMPT = """\
다음 질문을 분석해 처리 방식을 결정하세요.

route 선택지:
- doc_search: 사내 문서에서 정보를 찾는 질문 (정책, 절차, 규정, 가이드 등)
- tool_call: 실제 작업을 수행하는 요청 (예약, 조회, 실행, 전송 등 동작)
- web_search: 외부 최신 정보가 필요한 질문 (사내 문서에 없는 일반 지식, 뉴스 등)

strategy 선택지 (doc_search에만 적용, 그 외는 none):
- none: 질문이 단순하고 명확해 그대로 검색
- multi_query: 질문이 복잡하거나 여러 항목 비교/열거 → 하위 쿼리로 분해 검색

출력 형식: <route>:<strategy>
예시: doc_search:none, doc_search:multi_query, web_search:none, tool_call:none
다른 텍스트 없이 위 형식만 출력하세요.

질문: {question}
출력:"""
```

파일 끝에 추가:
```python
MULTI_QUERY_PROMPT = """\
다음 질문을 사내 문서 검색에 최적화된 2~3개의 독립적인 하위 쿼리로 분해하세요.
각 쿼리는 단독으로 검색해도 의미가 통하는 완전한 문장이어야 합니다.
각 쿼리를 줄바꿈으로 구분해 출력하세요. 번호나 기호 없이 쿼리만 출력하세요.

질문: {question}
하위 쿼리:"""
```

- [ ] **Step 2: 문법 오류 없는지 확인**

```bash
python -c "from app.graph.prompts import ROUTER_PROMPT, MULTI_QUERY_PROMPT; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: 커밋**

```bash
git add app/graph/prompts.py
git commit -m "feat(prompts): ROUTER_PROMPT에 strategy 출력 형식 추가, MULTI_QUERY_PROMPT 신설"
```

---

## Task 3: router_node — rewrite_strategy 출력 추가

**Files:**
- Modify: `app/graph/nodes/router.py`
- Modify: `tests/app/graph/nodes/test_router.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/app/graph/nodes/test_router.py` 끝에 다음을 추가:

```python
def test_router_outputs_rewrite_strategy_none():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "doc_search:none"

    result = router_node({"rewritten_question": "연차 정책이 뭐야?"}, llm=mock_llm)

    assert result["route"] == "doc_search"
    assert result["rewrite_strategy"] == "none"


def test_router_outputs_rewrite_strategy_multi_query():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "doc_search:multi_query"

    result = router_node({"rewritten_question": "연차와 병가의 차이를 비교해줘"}, llm=mock_llm)

    assert result["route"] == "doc_search"
    assert result["rewrite_strategy"] == "multi_query"


def test_router_strategy_defaults_to_none_on_unknown():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "doc_search:invalid_strategy"

    result = router_node({"rewritten_question": "질문"}, llm=mock_llm)

    assert result["rewrite_strategy"] == "none"


def test_router_web_search_has_none_strategy():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "web_search:none"

    result = router_node({"rewritten_question": "최신 뉴스"}, llm=mock_llm)

    assert result["route"] == "web_search"
    assert result["rewrite_strategy"] == "none"


def test_router_backward_compat_single_word_response():
    """구형 LLM이 전략 없이 route만 반환해도 동작해야 한다."""
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "doc_search"

    result = router_node({"rewritten_question": "연차"}, llm=mock_llm)

    assert result["route"] == "doc_search"
    assert result["rewrite_strategy"] == "none"
```

- [ ] **Step 2: 테스트 실행 → FAIL 확인**

```bash
pytest tests/app/graph/nodes/test_router.py -v -k "strategy"
```

Expected: `FAILED — KeyError: 'rewrite_strategy'`

- [ ] **Step 3: router_node 구현 수정**

`app/graph/nodes/router.py` 전체를 다음으로 교체:

```python
from shared.llm.base import LLMClient
from app.graph.prompts import ROUTER_PROMPT

_VALID_ROUTES = {"doc_search", "web_search", "tool_call"}
_VALID_STRATEGIES = {"none", "contextual", "multi_query"}


def router_node(state: dict, *, llm: LLMClient) -> dict:
    prompt = ROUTER_PROMPT.format(question=state["rewritten_question"])
    response = llm.complete(prompt).strip().lower()

    parts = response.split(":")
    route_raw = parts[0].strip()
    strategy_raw = parts[1].strip() if len(parts) > 1 else "none"

    route = route_raw if route_raw in _VALID_ROUTES else "doc_search"
    strategy = strategy_raw if strategy_raw in _VALID_STRATEGIES else "none"
    tool_input = state["rewritten_question"] if route == "tool_call" else ""

    return {"route": route, "rewrite_strategy": strategy, "tool_input": tool_input}
```

- [ ] **Step 4: 전체 router 테스트 실행 → PASS 확인**

```bash
pytest tests/app/graph/nodes/test_router.py tests/app/graph/nodes/test_router_edge_cases.py -v
```

Expected: 모든 테스트 PASS

- [ ] **Step 5: 커밋**

```bash
git add app/graph/nodes/router.py tests/app/graph/nodes/test_router.py
git commit -m "feat(router): rewrite_strategy 출력 추가 (none/multi_query)"
```

---

## Task 4: multi_query_node 신설

**Files:**
- Create: `app/graph/nodes/multi_query.py`
- Create: `tests/app/graph/nodes/test_multi_query.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/app/graph/nodes/test_multi_query.py` 생성:

```python
from unittest.mock import MagicMock

from app.graph.nodes.multi_query import multi_query_node


def test_multi_query_returns_list_of_queries():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "연차 신청 방법\n연차 일수 정책\n연차 신청 기한"

    result = multi_query_node({"rewritten_question": "연차 관련 정책 전부 알려줘"}, llm=mock_llm)

    assert "multi_queries" in result
    assert len(result["multi_queries"]) == 3
    assert result["multi_queries"][0] == "연차 신청 방법"


def test_multi_query_strips_whitespace_from_each_query():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "  병가 신청 절차  \n  병가 최대 일수  "

    result = multi_query_node({"rewritten_question": "병가 관련 알려줘"}, llm=mock_llm)

    assert result["multi_queries"] == ["병가 신청 절차", "병가 최대 일수"]


def test_multi_query_caps_at_three_queries():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "q1\nq2\nq3\nq4\nq5"

    result = multi_query_node({"rewritten_question": "복잡한 질문"}, llm=mock_llm)

    assert len(result["multi_queries"]) == 3


def test_multi_query_falls_back_to_original_on_empty_response():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "   "

    result = multi_query_node({"rewritten_question": "연차 정책"}, llm=mock_llm)

    assert result["multi_queries"] == ["연차 정책"]


def test_multi_query_uses_rewritten_question_in_prompt():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "쿼리1"

    multi_query_node({"rewritten_question": "재작성된 질문 내용"}, llm=mock_llm)

    prompt = mock_llm.complete.call_args[0][0]
    assert "재작성된 질문 내용" in prompt


def test_multi_query_falls_back_to_question_when_no_rewritten():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "쿼리1"

    multi_query_node({"question": "원본 질문", "rewritten_question": ""}, llm=mock_llm)

    prompt = mock_llm.complete.call_args[0][0]
    assert "원본 질문" in prompt


def test_multi_query_ignores_empty_lines():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "쿼리1\n\n쿼리2\n\n"

    result = multi_query_node({"rewritten_question": "질문"}, llm=mock_llm)

    assert result["multi_queries"] == ["쿼리1", "쿼리2"]
```

- [ ] **Step 2: 테스트 실행 → FAIL 확인**

```bash
pytest tests/app/graph/nodes/test_multi_query.py -v
```

Expected: `ImportError: cannot import name 'multi_query_node'`

- [ ] **Step 3: multi_query_node 구현**

`app/graph/nodes/multi_query.py` 생성:

```python
from shared.llm.base import LLMClient
from app.graph.prompts import MULTI_QUERY_PROMPT


def multi_query_node(state: dict, *, llm: LLMClient) -> dict:
    question = state.get("rewritten_question") or state.get("question", "")
    prompt = MULTI_QUERY_PROMPT.format(question=question)
    response = llm.complete(prompt).strip()

    queries = [q.strip() for q in response.splitlines() if q.strip()]
    if not queries:
        queries = [question]

    return {"multi_queries": queries[:3]}
```

- [ ] **Step 4: 테스트 실행 → PASS 확인**

```bash
pytest tests/app/graph/nodes/test_multi_query.py -v
```

Expected: `7 passed`

- [ ] **Step 5: 커밋**

```bash
git add app/graph/nodes/multi_query.py tests/app/graph/nodes/test_multi_query.py
git commit -m "feat(multi_query): multi_query_node 신설 — 하위 쿼리 분해 노드"
```

---

## Task 5: retrieve_node — multi-query 병렬 검색 + RRF merge

**Files:**
- Modify: `app/graph/nodes/retrieve.py`
- Modify: `tests/app/graph/nodes/test_retrieve.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/app/graph/nodes/test_retrieve.py` 끝에 다음을 추가:

```python
@pytest.mark.asyncio
async def test_retrieve_node_multi_query_calls_retriever_per_query():
    mock_retriever = MagicMock()
    mock_retriever.retrieve = AsyncMock(return_value=[])
    mock_fga = _mock_fga()

    state = {
        "question": "원본",
        "rewritten_question": "재작성",
        "multi_queries": ["쿼리1", "쿼리2", "쿼리3"],
        "user_id": "u1",
        "user_teams": [],
        "personal_doc_ids": [],
    }
    await retrieve_node(state, retriever=mock_retriever, fga_client=mock_fga)

    assert mock_retriever.retrieve.call_count == 3


@pytest.mark.asyncio
async def test_retrieve_node_multi_query_merges_results_via_rrf():
    from shared.models import Chunk

    def _sr(cid: str) -> SearchResult:
        return SearchResult(chunk=Chunk(text="t", source=cid, chunk_id=cid), score=0.9)

    mock_retriever = MagicMock()
    # q1 → [a, b], q2 → [b, c]: b는 양쪽에 등장 → RRF 점수 높음
    mock_retriever.retrieve = AsyncMock(side_effect=[
        [_sr("a"), _sr("b")],
        [_sr("b"), _sr("c")],
    ])
    mock_fga = _mock_fga()

    state = {
        "question": "원본",
        "rewritten_question": "재작성",
        "multi_queries": ["쿼리1", "쿼리2"],
        "user_id": "u1",
        "user_teams": [],
        "personal_doc_ids": [],
    }
    result = await retrieve_node(state, retriever=mock_retriever, fga_client=mock_fga, top_k=10)
    chunk_ids = [r.chunk.chunk_id for r in result["documents"]]
    # b는 두 리스트 모두에 등장하므로 RRF 상위 순위여야 함
    assert chunk_ids[0] == "b"


@pytest.mark.asyncio
async def test_retrieve_node_single_query_when_multi_queries_empty():
    mock_retriever = MagicMock()
    mock_retriever.retrieve = AsyncMock(return_value=[_make_result()])
    mock_fga = _mock_fga()

    state = {
        "question": "원본",
        "rewritten_question": "재작성",
        "multi_queries": [],
        "user_id": "u1",
        "user_teams": [],
        "personal_doc_ids": [],
    }
    await retrieve_node(state, retriever=mock_retriever, fga_client=mock_fga)

    assert mock_retriever.retrieve.call_count == 1
    assert mock_retriever.retrieve.call_args[0][0] == "재작성"
```

- [ ] **Step 2: 테스트 실행 → FAIL 확인**

```bash
pytest tests/app/graph/nodes/test_retrieve.py -v -k "multi_query"
```

Expected: `FAILED — AssertionError: assert call_count == 3` (현재 1회만 호출)

- [ ] **Step 3: retrieve_node 구현 수정**

`app/graph/nodes/retrieve.py` 전체를 다음으로 교체:

```python
import asyncio

from shared.fga.client import FGAClient
from shared.fga.models import UserPermission
from shared.models import SearchResult
from shared.reranker.base import Reranker
from shared.reranker.noop_reranker import NoOpReranker
from shared.retriever.base import Retriever


def _rrf_merge(ranked_lists: list[list[SearchResult]], k: int = 60) -> list[SearchResult]:
    """Reciprocal Rank Fusion — 여러 ranked list를 하나로 병합."""
    rrf_scores: dict[str, float] = {}
    best_result: dict[str, SearchResult] = {}
    for ranked_list in ranked_lists:
        for rank, result in enumerate(ranked_list, start=1):
            key = result.chunk.chunk_id
            rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (k + rank)
            if key not in best_result:
                best_result[key] = result
    return sorted(
        best_result.values(),
        key=lambda r: rrf_scores[r.chunk.chunk_id],
        reverse=True,
    )


async def retrieve_node(
    state: dict,
    *,
    retriever: Retriever,
    fga_client: FGAClient,
    reranker: Reranker | None = None,
    retrieve_top_k: int = 20,
    top_k: int = 5,
) -> dict:
    perm = UserPermission(
        user_id=state.get("user_id", "anonymous"),
        teams=state.get("user_teams", []),
        personal_docs=state.get("personal_doc_ids", []),
    )
    where_clause, params = fga_client.build_pg_filter(perm)

    multi_queries: list[str] = state.get("multi_queries") or []

    if multi_queries:
        all_results: tuple[list[SearchResult], ...] = await asyncio.gather(*[
            retriever.retrieve(q, top_k=retrieve_top_k, where_clause=where_clause, params=params)
            for q in multi_queries
        ])
        results = _rrf_merge(list(all_results))
        primary_query = multi_queries[0]
    else:
        primary_query = state.get("rewritten_question") or state["question"]
        results = await retriever.retrieve(
            primary_query, top_k=retrieve_top_k, where_clause=where_clause, params=params
        )

    _reranker = reranker or NoOpReranker()
    reranked = _reranker.rerank(primary_query, results, top_k=top_k)
    return {"documents": reranked}
```

- [ ] **Step 4: 전체 retrieve 테스트 실행 → PASS 확인**

```bash
pytest tests/app/graph/nodes/test_retrieve.py -v
```

Expected: 모든 테스트 PASS (기존 4개 + 신규 3개)

- [ ] **Step 5: 커밋**

```bash
git add app/graph/nodes/retrieve.py tests/app/graph/nodes/test_retrieve.py
git commit -m "feat(retrieve): multi-query 병렬 검색 + RRF merge 지원"
```

---

## Task 6: edges.py — route_after_router multi_query 분기 추가

**Files:**
- Modify: `app/graph/edges.py`
- Modify: `tests/app/graph/test_edges.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/app/graph/test_edges.py` 의 `route_after_router` 섹션 끝에 추가:

```python
def test_route_after_router_returns_multi_query_when_strategy_set():
    state = {"route": "doc_search", "rewrite_strategy": "multi_query"}
    assert route_after_router(state) == "multi_query"


def test_route_after_router_returns_doc_search_when_strategy_none():
    state = {"route": "doc_search", "rewrite_strategy": "none"}
    assert route_after_router(state) == "doc_search"


def test_route_after_router_returns_doc_search_when_no_strategy_key():
    """rewrite_strategy 키가 없어도 기존 동작 유지."""
    state = {"route": "doc_search"}
    assert route_after_router(state) == "doc_search"
```

- [ ] **Step 2: 테스트 실행 → FAIL 확인**

```bash
pytest tests/app/graph/test_edges.py::test_route_after_router_returns_multi_query_when_strategy_set -v
```

Expected: `FAILED — AssertionError: assert 'doc_search' == 'multi_query'`

- [ ] **Step 3: route_after_router 수정**

`app/graph/edges.py` 의 `route_after_router` 함수를 다음으로 교체:

```python
def route_after_router(state: dict) -> str:
    """Route based on router decision and rewrite strategy.

    Args:
        state: Graph state containing route and rewrite_strategy fields

    Returns:
        "multi_query" if doc_search route with multi_query strategy,
        otherwise the route value from state
    """
    route = state["route"]
    if route == "doc_search" and state.get("rewrite_strategy") == "multi_query":
        return "multi_query"
    return route
```

- [ ] **Step 4: 전체 edges 테스트 실행 → PASS 확인**

```bash
pytest tests/app/graph/test_edges.py -v
```

Expected: 모든 테스트 PASS (기존 + 신규 3개)

- [ ] **Step 5: 커밋**

```bash
git add app/graph/edges.py tests/app/graph/test_edges.py
git commit -m "feat(edges): route_after_router에 multi_query 분기 추가"
```

---

## Task 7: builder.py — multi_query 노드 등록 및 초기 state 갱신

**Files:**
- Modify: `app/graph/builder.py`
- Modify: `tests/app/graph/test_builder.py`

- [ ] **Step 1: _make_initial_state 업데이트 (테스트 헬퍼)**

`tests/app/graph/test_builder.py` 의 `_make_initial_state` 함수를 다음으로 교체:

```python
def _make_initial_state(question: str) -> dict:
    return {
        "question": question,
        "rewritten_question": "",
        "chat_history": [],
        "route": "doc_search",
        "rewrite_strategy": None,
        "multi_queries": [],
        "documents": [],
        "relevance_score": 0.0,
        "retry_count": 0,
        "answer": "",
        "citations": [],
        "hallucination_passed": False,
        "confirmed": False,
        "tool_input": "",
        "user_id": "anonymous",
        "allowed_doc_ids": [],
        "user_teams": [],
        "personal_doc_ids": [],
    }
```

- [ ] **Step 2: builder.py 수정 — import 추가**

`app/graph/builder.py` 의 import 섹션에 `multi_query_node` 추가:

기존:
```python
from app.graph.nodes.tool_executor import tool_executor_node
from app.graph.nodes.web_search import web_search_node
```

교체:
```python
from app.graph.nodes.multi_query import multi_query_node
from app.graph.nodes.tool_executor import tool_executor_node
from app.graph.nodes.web_search import web_search_node
```

- [ ] **Step 3: builder.py 수정 — 노드 등록 + 엣지 갱신**

`build_graph` 함수 내에서 다음 두 군데를 수정:

(a) `g.add_node("web_search", ...)` 바로 앞에 추가:
```python
    g.add_node("multi_query", partial(multi_query_node, llm=llm))
```

(b) 기존 conditional edges:
```python
    g.add_conditional_edges(
        "router",
        route_after_router,
        {"doc_search": "permission", "web_search": "web_search", "tool_call": "confirm"},
    )
```

교체:
```python
    g.add_conditional_edges(
        "router",
        route_after_router,
        {
            "doc_search": "permission",
            "multi_query": "multi_query",
            "web_search": "web_search",
            "tool_call": "confirm",
        },
    )
    g.add_edge("multi_query", "permission")
```

- [ ] **Step 4: builder.py 수정 — answer_question 초기 state 갱신**

`answer_question` 함수의 `initial: AgentState = { ... }` 블록에 추가:

기존:
```python
    initial: AgentState = {
        "question": question,
        "rewritten_question": "",
        "chat_history": chat_history,
        "route": "doc_search",
        "documents": [],
```

교체:
```python
    initial: AgentState = {
        "question": question,
        "rewritten_question": "",
        "chat_history": chat_history,
        "route": "doc_search",
        "rewrite_strategy": None,
        "multi_queries": [],
        "documents": [],
```

- [ ] **Step 5: builder.py 수정 — stream_answer 초기 state 갱신**

`stream_answer` 함수의 `initial: AgentState = { ... }` 블록에도 동일하게:

기존:
```python
        initial: AgentState = {
            "question": question,
            "rewritten_question": "",
            "chat_history": chat_history,
            "route": "doc_search",
            "documents": [],
```

교체:
```python
        initial: AgentState = {
            "question": question,
            "rewritten_question": "",
            "chat_history": chat_history,
            "route": "doc_search",
            "rewrite_strategy": None,
            "multi_queries": [],
            "documents": [],
```

- [ ] **Step 6: 빌드 오류 없는지 확인**

```bash
python -c "from app.graph.builder import build_graph; print('OK')"
```

Expected: `OK`

- [ ] **Step 7: 전체 테스트 실행 → PASS 확인**

```bash
pytest tests/app/graph/ -v --tb=short
```

Expected: 모든 테스트 PASS

- [ ] **Step 8: 커밋**

```bash
git add app/graph/builder.py tests/app/graph/test_builder.py
git commit -m "feat(builder): multi_query 노드 등록 및 conditional edges 갱신"
```

---

## Task 8: 전체 회귀 테스트 + eval 확인

- [ ] **Step 1: 전체 단위 테스트 실행**

```bash
cd /Users/acacian/vscode/company-rag
pytest tests/ -v --tb=short -q
```

Expected: 모든 테스트 PASS (실패 0개)

- [ ] **Step 2: eval 회귀 점수 확인**

```bash
python tests/eval/runner.py 2>&1 | tail -20
```

기준선 대비 하락 시 원인 명시 후 ADR 또는 주석에 기록.

- [ ] **Step 3: 최종 커밋 (태그 없음 — Phase 태그는 PR merge 후)**

```bash
git add -A
git commit -m "chore: multi-query rewriting 구현 완료 — 회귀 테스트 통과"
```

---

## Self-Review 체크리스트

### 1. Spec 커버리지

| 백로그 항목 | 구현 Task |
|------------|-----------|
| Router Node에 재작성 판단 로직 추가 | Task 2 (프롬프트) + Task 3 (router_node) + Task 6 (edges) |
| Contextual Query Rewriter 노드 신설 | 기존 `rewrite_query_node`이 이미 수행 — 별도 신설 불필요 |
| Multi-Query + RRF 검색 | Task 4 (multi_query_node) + Task 5 (retrieve_node) |
| 경량 LLM 분리 | builder.py에서 `llm=llm` 통일 — 별도 `light_llm` 파라미터는 Medium 백로그로 이동 |

### 2. Placeholder 없음 확인 ✅

모든 Step에 실제 코드 포함.

### 3. 타입 일관성

- `multi_queries: list[str]` — Task 1(state), Task 4(node 출력), Task 5(node 입력) 일치 ✅
- `rewrite_strategy: Literal["none", "contextual", "multi_query"] | None` — Task 1, Task 3 일치 ✅
- `route_after_router` 반환값 `"multi_query"` — Task 6(edges), Task 7(builder conditional dict) 일치 ✅
