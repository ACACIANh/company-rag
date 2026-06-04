# 설계: 라우터 모호 질문 재확인 (Clarify Node)

## 목표

`router_node`가 `doc_search`와 `agent` 중 하나를 확신하지 못할 때, 사용자에게 한글 선택지를 제시해 의도를 확인한 뒤 올바른 경로로 진행한다.

---

## 1. 상태 스키마 변경

`AgentState`에 필드 1개 추가:

```python
route_confidence: float   # router_node가 채움. 0.0~1.0.
```

---

## 2. `router_node` 변경

### LLM 출력 형식

기존: `"doc_search:none"`  
신규: `"doc_search:none:0.8"` (루트:전략:확신도)

### 로직

```python
_CLARIFY_THRESHOLD = 0.75
_VALID_ROUTES = {"doc_search", "agent", "capability", "clarify"}

def router_node(state, *, llm):
    response = llm.complete(prompt).strip().lower()
    parts = response.split(":")

    route_raw    = parts[0].strip()
    strategy_raw = parts[1].strip() if len(parts) > 1 else "none"
    confidence   = float(parts[2].strip()) if len(parts) > 2 else 1.0

    route    = route_raw if route_raw in _VALID_ROUTES else "doc_search"
    strategy = strategy_raw if strategy_raw in _VALID_STRATEGIES else "none"

    # capability는 clarify 대상 제외
    if confidence < _CLARIFY_THRESHOLD and route in {"doc_search", "agent"}:
        return {"route": "clarify", "route_confidence": confidence, ...}

    return {"route": route, "route_confidence": confidence, ...}
```

### ROUTER_PROMPT 변경

출력 형식 지시 추가:

```
출력 형식: <route>:<strategy>:<확신도 0.0~1.0>
예시:
- "doc_search:none:0.9"  → 문서 검색, 확신
- "agent:none:0.6"       → DB 조회이나 불확실
- "doc_search:none:0.5"  → 애매한 경우
```

---

## 3. `clarify_node` 신규 노드

파일: `app/graph/nodes/clarify.py`

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
    return {"route": _CLARIFY_OPTIONS[label]}
```

사용자 눈에는 한글 버튼만 보이고, 내부 `route`는 기존 `"doc_search"` / `"agent"` 그대로 유지.

---

## 4. 엣지 변경

### `route_after_router`

```python
def route_after_router(state: dict) -> str:
    route = state["route"]
    if route == "clarify":
        return "clarify"
    if route == "doc_search" and state.get("rewrite_strategy") == "multi_query":
        return "multi_query"
    return route
```

### 그래프 배선

```
router_node
  ├─ clarify    → clarify_node
  ├─ doc_search → retrieve
  ├─ multi_query → multi_query_node
  ├─ agent      → agent_node
  └─ capability → capability_node

clarify_node
  ├─ doc_search → retrieve
  └─ agent      → agent_node
```

`clarify_node` 이후 분기는 `route_after_router`를 재호출하지 않고, `clarify_node` 출력의 `route` 값으로 직접 분기하는 조건부 엣지 추가.

---

## 5. ADR

- `interrupt()` 사용 범위를 agent 도구 경로 → **라우터 분기 단계까지 확장**
- 기존 CLAUDE.md "agent 경로에만" 제약을 이 ADR로 공식 완화

---

## 6. 테스트

| 케이스 | 기대 결과 |
|--------|-----------|
| 확신도 < 0.75, route=doc_search | `route="clarify"` |
| 확신도 < 0.75, route=agent | `route="clarify"` |
| 확신도 < 0.75, route=capability | clarify 미트리거, `route="capability"` |
| 확신도 ≥ 0.75 | clarify 미트리거 |
| clarify_node: "사내 문서에서 찾기" 선택 | `route="doc_search"` |
| clarify_node: "업무 DB 조회 / 권한 도구 사용" 선택 | `route="agent"` |
| `route_after_router`: route="clarify" | `"clarify"` 반환 |
