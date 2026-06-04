# Router Clarify Ambiguous Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `router_node`이 `doc_search`/`agent` 분기를 확신하지 못할 때(확신도 < 0.75) 사용자에게 한글 선택지를 제시하고 의도를 확인한 뒤 올바른 경로로 재개한다.

**Architecture:** `router_node`가 LLM 출력 형식을 `루트:전략:확신도`로 확장해 파싱하고, 임계값 미만이면 `route="clarify"`를 반환한다. 새 `clarify_node`가 `interrupt()`로 한글 선택지를 제시하고 사용자 응답으로 `route`를 덮어쓴 뒤 기존 경로를 재개한다.

**Tech Stack:** Python 3.11, LangGraph (`interrupt`, `MemorySaver`), pytest

---

## File Map

| 역할 | 파일 | 변경 |
|------|------|------|
| 상태 스키마 | `app/graph/state.py` | `route_confidence` 필드 추가, `route` Literal 확장 |
| LLM 프롬프트 | `app/graph/prompts.py` | 출력 형식 `루트:전략:확신도` 추가 |
| 라우터 노드 | `app/graph/nodes/router.py` | 확신도 파싱 + clarify 트리거 |
| clarify 노드 | `app/graph/nodes/clarify.py` | 신규 |
| 엣지 함수 | `app/graph/edges.py` | `route_after_router` clarify 분기 추가 |
| 그래프 빌더 | `app/graph/builder.py` | clarify 노드/엣지 배선 |
| ADR | `docs/superpowers/decisions/ADR-0042-router-clarify-interrupt.md` | 신규 |
| 라우터 테스트 | `tests/app/graph/nodes/test_router.py` | 확신도 케이스 추가 |
| clarify 테스트 | `tests/app/graph/nodes/test_clarify.py` | 신규 |
| 엣지 테스트 | `tests/app/graph/test_edges.py` | clarify 분기 케이스 추가 |

---

## Task 1: ADR 작성

**Files:**
- Create: `docs/superpowers/decisions/ADR-0042-router-clarify-interrupt.md`

- [ ] **Step 1: ADR 파일 작성**

```markdown
# ADR-0042: 라우터 모호 질문 clarify — HITL 범위 확장

> **Status**: 🔵 승인됨

## 배경

기존 CLAUDE.md는 `interrupt()` 사용 범위를 "agent 도구 호출 경로에만"으로 제한한다.
그러나 라우터가 `doc_search`/`agent` 분기를 확신하지 못하는 경우(예: "연차 어떻게 해?"),
현재 설계는 `doc_search`로 silently fallback해 사용자 의도를 무시한다.

## 결정

`router_node`에서 확신도 < 0.75인 경우 `interrupt()`를 사용하는 `clarify_node`로
분기해 사용자에게 한글 선택지를 제시한다.

HITL 사용 범위를 **라우터 분기 단계까지 공식 확장**한다.

## 이유

- `capability` 루트는 ambiguous 할 일이 없으므로 clarify 대상 제외
- `MemorySaver` checkpointer는 이미 전체 그래프에 적용되어 있어 추가 작업 없음
- `confirm_node`와 interrupt payload 구조를 동형으로 유지해 프론트 렌더러 재사용

## 영향

- `app/graph/state.py`: `route_confidence: float` 필드 추가
- `app/graph/nodes/clarify.py` 신규
- `app/graph/edges.py`: `route_after_router` clarify 분기 추가
- `app/graph/builder.py`: clarify 노드/엣지 배선
- CLAUDE.md HITL 설명 갱신 필요
```

- [ ] **Step 2: ADR 인덱스 재생성**

```bash
cd /Users/acacian/vscode/company-rag/backend
.venv/bin/python -m scripts.gen_adr_index
```

- [ ] **Step 3: 커밋**

```bash
git add docs/superpowers/decisions/ADR-0042-router-clarify-interrupt.md \
        docs/superpowers/decisions/README.md
git commit -m "docs: ADR-0042 라우터 clarify interrupt HITL 범위 확장"
```

---

## Task 2: 상태 스키마 확장

**Files:**
- Modify: `app/graph/state.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/app/graph/nodes/test_router.py` 파일 상단에 추가:

```python
def test_router_returns_route_confidence_field():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "doc_search:none:0.9"
    result = router_node({"question": "연차 정책"}, llm=mock_llm)
    assert "route_confidence" in result
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
cd /Users/acacian/vscode/company-rag/backend
.venv/bin/python -m pytest tests/app/graph/nodes/test_router.py::test_router_returns_route_confidence_field -v
```
Expected: FAIL (`KeyError` 또는 `AssertionError`)

- [ ] **Step 3: `AgentState`에 필드 추가**

`app/graph/state.py`의 `AgentState` 클래스:

```python
# 기존
route: Literal["doc_search", "agent", "capability"]

# 변경
route: Literal["doc_search", "agent", "capability", "clarify"]
```

그리고 `executed_sql` 필드 아래에 추가:

```python
route_confidence: float          # router_node가 채움. 0.0~1.0. clarify_node가 읽음.
```

- [ ] **Step 4: 테스트 패스 확인** (아직 router_node를 수정하지 않았으므로 여전히 실패 — Task 3 완료 후 통과)

---

## Task 3: `router_node` 확신도 파싱 + clarify 트리거

**Files:**
- Modify: `app/graph/nodes/router.py`
- Modify: `tests/app/graph/nodes/test_router.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/app/graph/nodes/test_router.py` 에 추가:

```python
def test_router_parses_confidence_score():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "doc_search:none:0.9"
    result = router_node({"question": "연차 정책"}, llm=mock_llm)
    assert result["route"] == "doc_search"
    assert result["route_confidence"] == 0.9


def test_router_triggers_clarify_when_low_confidence_doc_search():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "doc_search:none:0.6"
    result = router_node({"question": "연차 어떻게 해?"}, llm=mock_llm)
    assert result["route"] == "clarify"
    assert result["route_confidence"] == 0.6


def test_router_triggers_clarify_when_low_confidence_agent():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "agent:none:0.5"
    result = router_node({"question": "데이터 보여줘"}, llm=mock_llm)
    assert result["route"] == "clarify"


def test_router_no_clarify_for_capability_regardless_of_confidence():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "capability:none:0.3"
    result = router_node({"question": "뭐 할 수 있어?"}, llm=mock_llm)
    assert result["route"] == "capability"


def test_router_no_clarify_at_exact_threshold():
    """확신도 == 0.75이면 clarify 미트리거."""
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "doc_search:none:0.75"
    result = router_node({"question": "연차 정책"}, llm=mock_llm)
    assert result["route"] == "doc_search"


def test_router_defaults_confidence_to_1_when_missing():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "doc_search:none"
    result = router_node({"question": "연차"}, llm=mock_llm)
    assert result["route_confidence"] == 1.0


def test_router_handles_invalid_confidence_gracefully():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "doc_search:none:abc"
    result = router_node({"question": "연차"}, llm=mock_llm)
    assert result["route_confidence"] == 1.0
    assert result["route"] == "doc_search"
```

- [ ] **Step 2: 실패 확인**

```bash
.venv/bin/python -m pytest tests/app/graph/nodes/test_router.py -k "confidence or clarify" -v
```
Expected: 모두 FAIL

- [ ] **Step 3: `router_node` 구현**

`app/graph/nodes/router.py` 전체 교체:

```python
from core.llm.base import LLMClient
from app.graph.prompts import ROUTER_PROMPT

_VALID_ROUTES = {"doc_search", "agent", "capability"}
_VALID_STRATEGIES = {"none", "contextual", "multi_query"}
_CLARIFY_THRESHOLD = 0.75


def router_node(state: dict, *, llm: LLMClient) -> dict:
    # 라우팅·도구입력은 원본 질문으로 — rewrite(문서검색 편향) 비결정성 차단 (ADR-0031)
    prompt = ROUTER_PROMPT.format(question=state["question"])
    response = llm.complete(prompt).strip().lower()

    parts = response.split(":")
    route_raw    = parts[0].strip()
    strategy_raw = parts[1].strip() if len(parts) > 1 else "none"
    try:
        confidence = float(parts[2].strip()) if len(parts) > 2 else 1.0
    except ValueError:
        confidence = 1.0

    route    = route_raw if route_raw in _VALID_ROUTES else "doc_search"
    strategy = strategy_raw if strategy_raw in _VALID_STRATEGIES else "none"

    if confidence < _CLARIFY_THRESHOLD and route in {"doc_search", "agent"}:
        return {
            "route": "clarify",
            "route_confidence": confidence,
            "rewrite_strategy": strategy,
            "tool_input": "",
        }

    tool_input = state["question"] if route == "agent" else ""
    return {
        "route": route,
        "route_confidence": confidence,
        "rewrite_strategy": strategy,
        "tool_input": tool_input,
    }
```

- [ ] **Step 4: 테스트 패스 확인**

```bash
.venv/bin/python -m pytest tests/app/graph/nodes/test_router.py -v
```
Expected: 모두 PASS

- [ ] **Step 5: 커밋**

```bash
git add app/graph/state.py app/graph/nodes/router.py \
        tests/app/graph/nodes/test_router.py
git commit -m "feat: router_node 확신도 파싱 및 clarify 트리거 (ADR-0042)"
```

---

## Task 4: ROUTER_PROMPT 출력 형식 업데이트

**Files:**
- Modify: `app/graph/prompts.py`

- [ ] **Step 1: 프롬프트 수정**

`app/graph/prompts.py`에서 ROUTER_PROMPT의 출력 형식 섹션을 교체:

```
# 기존
출력 형식: <route>:<strategy>
예시: doc_search:none, doc_search:multi_query, agent:none, capability:none
다른 텍스트 없이 위 형식만 출력하세요.

# 변경
출력 형식: <route>:<strategy>:<확신도>
- 확신도: 0.0(완전 불확실) ~ 1.0(완전 확신), 소수점 두 자리
- 경계 예시에서 명확한 경우 0.9 이상, 애매한 경우 0.5~0.7
예시: doc_search:none:0.95, doc_search:multi_query:0.85, agent:none:0.90, capability:none:1.0
다른 텍스트 없이 위 형식만 출력하세요.
```

- [ ] **Step 2: 기존 테스트 전체 패스 확인**

```bash
.venv/bin/python -m pytest tests/app/graph/nodes/test_router.py -v
```
Expected: 모두 PASS (backward compat: 확신도 없는 응답도 처리됨)

- [ ] **Step 3: 커밋**

```bash
git add app/graph/prompts.py
git commit -m "feat: ROUTER_PROMPT 출력 형식에 확신도 추가 (ADR-0042)"
```

---

## Task 5: `clarify_node` 신규

**Files:**
- Create: `app/graph/nodes/clarify.py`
- Create: `tests/app/graph/nodes/test_clarify.py`

- [ ] **Step 1: 실패 테스트 작성**

새 파일 `tests/app/graph/nodes/test_clarify.py`:

```python
from unittest.mock import patch

from app.graph.nodes.clarify import clarify_node


def test_clarify_node_maps_doc_search_label():
    with patch("app.graph.nodes.clarify.interrupt", return_value="사내 문서에서 찾기"):
        result = clarify_node({"question": "연차 어떻게 해?"})
    assert result["route"] == "doc_search"
    assert result["tool_input"] == ""


def test_clarify_node_maps_agent_label_and_sets_tool_input():
    with patch("app.graph.nodes.clarify.interrupt", return_value="업무 DB 조회 / 권한 도구 사용"):
        result = clarify_node({"question": "연차 어떻게 해?"})
    assert result["route"] == "agent"
    assert result["tool_input"] == "연차 어떻게 해?"


def test_clarify_node_interrupt_payload_includes_question():
    captured = {}

    def fake_interrupt(payload):
        captured["payload"] = payload
        return "사내 문서에서 찾기"

    with patch("app.graph.nodes.clarify.interrupt", side_effect=fake_interrupt):
        clarify_node({"question": "연차 어떻게 해?"})

    assert "연차 어떻게 해?" in captured["payload"]["message"]


def test_clarify_node_interrupt_options_are_korean():
    captured = {}

    def fake_interrupt(payload):
        captured["payload"] = payload
        return "사내 문서에서 찾기"

    with patch("app.graph.nodes.clarify.interrupt", side_effect=fake_interrupt):
        clarify_node({"question": "질문"})

    assert set(captured["payload"]["options"]) == {
        "사내 문서에서 찾기",
        "업무 DB 조회 / 권한 도구 사용",
    }
```

- [ ] **Step 2: 실패 확인**

```bash
.venv/bin/python -m pytest tests/app/graph/nodes/test_clarify.py -v
```
Expected: `ModuleNotFoundError` (파일 미존재)

- [ ] **Step 3: `clarify_node` 구현**

새 파일 `app/graph/nodes/clarify.py`:

```python
from langgraph.types import interrupt

_CLARIFY_OPTIONS = {
    "사내 문서에서 찾기": "doc_search",
    "업무 DB 조회 / 권한 도구 사용": "agent",
}


def clarify_node(state: dict) -> dict:
    question = state["question"]
    label = interrupt({
        "message": f'"{question}" — 어떤 방식으로 처리할까요?',
        "options": list(_CLARIFY_OPTIONS.keys()),
    })
    route = _CLARIFY_OPTIONS[label]
    # agent 경로로 분기 시 tool_input 채움 — router_node와 동일 계약 (ADR-0031)
    return {
        "route": route,
        "tool_input": question if route == "agent" else "",
    }
```

- [ ] **Step 4: 테스트 패스 확인**

```bash
.venv/bin/python -m pytest tests/app/graph/nodes/test_clarify.py -v
```
Expected: 모두 PASS

- [ ] **Step 5: 커밋**

```bash
git add app/graph/nodes/clarify.py tests/app/graph/nodes/test_clarify.py
git commit -m "feat: clarify_node 한글 선택지 interrupt 신규 (ADR-0042)"
```

---

## Task 6: `route_after_router` clarify 분기 추가

**Files:**
- Modify: `app/graph/edges.py`
- Modify: `tests/app/graph/test_edges.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/app/graph/test_edges.py`에 추가:

```python
def test_route_after_router_returns_clarify():
    assert route_after_router({"route": "clarify"}) == "clarify"
```

- [ ] **Step 2: 실패 확인**

```bash
.venv/bin/python -m pytest tests/app/graph/test_edges.py::test_route_after_router_returns_clarify -v
```
Expected: FAIL (`AssertionError` — 현재 `route_after_router`가 `"clarify"`를 그대로 반환하긴 하나, multi_query 분기 앞에 명시적 처리가 없어 통과 가능성 있음. 실제 실패 여부 확인 후 다음 스텝 진행)

- [ ] **Step 3: `route_after_router` 명시적 clarify 분기 추가**

`app/graph/edges.py`의 `route_after_router`:

```python
def route_after_router(state: dict) -> str:
    route = state["route"]
    if route == "clarify":
        return "clarify"
    if route == "doc_search" and state.get("rewrite_strategy") == "multi_query":
        return "multi_query"
    return route
```

- [ ] **Step 4: 전체 엣지 테스트 패스 확인**

```bash
.venv/bin/python -m pytest tests/app/graph/test_edges.py -v
```
Expected: 모두 PASS

- [ ] **Step 5: 커밋**

```bash
git add app/graph/edges.py tests/app/graph/test_edges.py
git commit -m "feat: route_after_router clarify 분기 추가 (ADR-0042)"
```

---

## Task 7: `builder.py` clarify 노드/엣지 배선

**Files:**
- Modify: `app/graph/builder.py`

- [ ] **Step 1: import 추가**

`app/graph/builder.py` 상단 import 섹션에 추가:

```python
from app.graph.nodes.clarify import clarify_node
```

- [ ] **Step 2: 노드 등록**

`g.add_node("capability", capability_node)` 바로 위에 추가:

```python
g.add_node("clarify", clarify_node)
```

- [ ] **Step 3: router conditional_edges에 clarify 추가**

기존:

```python
g.add_conditional_edges(
    "router",
    route_after_router,
    {
        "doc_search": "permission",
        "multi_query": "multi_query",
        "agent": "agent",
        "capability": "capability",
    },
)
```

변경:

```python
g.add_conditional_edges(
    "router",
    route_after_router,
    {
        "doc_search": "permission",
        "multi_query": "multi_query",
        "agent": "agent",
        "capability": "capability",
        "clarify": "clarify",
    },
)
```

- [ ] **Step 4: clarify 아웃고잉 엣지 추가**

`g.add_edge("multi_query", "permission")` 바로 아래에 추가:

```python
g.add_conditional_edges(
    "clarify",
    lambda state: state["route"],
    {
        "doc_search": "permission",
        "agent": "agent",
    },
)
```

- [ ] **Step 5: 전체 테스트 패스 확인**

```bash
.venv/bin/python -m pytest tests/ -v --tb=short
```
Expected: 모두 PASS

- [ ] **Step 6: 커밋**

```bash
git add app/graph/builder.py
git commit -m "feat: builder.py clarify 노드/엣지 배선 완료 (ADR-0042)"
```

---

## Task 8: CLAUDE.md HITL 설명 갱신

**Files:**
- Modify: `CLAUDE.md` (backend)

- [ ] **Step 1: HITL 항목 수정**

`backend/CLAUDE.md`의 HITL 항목:

```
# 기존
- HITL: `interrupt()` — agent(도구 호출) 경로에만, `MemorySaver` checkpointer 필수 (`app/graph/nodes/confirm.py`)

# 변경
- HITL: `interrupt()` — (1) agent 도구 호출 경로(`confirm.py`), (2) 라우터 모호 분기(`clarify.py`). `MemorySaver` checkpointer 필수. (ADR-0042)
```

- [ ] **Step 2: 커밋**

```bash
git add CLAUDE.md
git commit -m "docs: CLAUDE.md HITL 범위 갱신 (ADR-0042)"
```
