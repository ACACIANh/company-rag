# ADR-0042: 라우터 모호 질문 clarify — HITL 범위 확장

> **Status**: 🔵 승인됨

**Date**: 2026-06-04

## Context

현재 CLAUDE.md는 `interrupt()` 사용 범위를 **"agent 도구 호출 경로에만"**으로 제한한다(ADR-0027).
그러나 라우터가 `doc_search`/`agent` 분기를 확신하지 못하는 경우(예: "연차 어떻게 해?", "이번 분기 목표가 뭐야?"),
현재 설계는 `doc_search`로 silently fallback해 사용자 의도를 무시하고 검색만 시도한다.

이는 UX 측면에서:
1. 사용자가 agent를 기대했을 때 도구 호출 없이 검색만 반환 → 답답함
2. 의도 파악 → 재질문 사이클 발생

## Options

| 선택지 | 트레이드오프 | 선택 |
|--------|------------|------|
| **A. router에 clarify 분기 추가** (interrupt() 범위 확장) | HITL 범위 확장, checkpointer 이미 전역 적용, 프론트 payload 구조 동형화 필요, 구현 작업 추가 | ✅ |
| B. router 확신도 임계값 상향 (0.75 → 0.9) | 보류 답변 증가, 해결 아님 |  |
| C. RAG 검색만으로도 충분하게 개선 | 근본 해결 아님, 하이브리드 검색·리랭킹 비용 |  |

## Decision

**선택: A — router에 clarify 분기 추가**

`router_node`에서 확신도 < 0.75인 경우 기존 `doc_search`/`agent` 분기 대신
새 `clarify` 엣지로 라우팅해 `clarify_node`에서 사용자에게 한글 선택지를 제시한다.

### 설계 상세

1. **상태 확장** (`app/graph/state.py`):
   ```python
   class AgentState(TypedDict):
       ...
       route_confidence: float  # router_node에서 설정, [0, 1]
   ```

2. **라우터 출력 형식** (ROUTER_PROMPT 갱신):
   ```json
   {
       "route": "doc_search|agent|clarify",
       "confidence": 0.85,
       "reasoning": "..."
   }
   ```
   - 기존: `{"route": "doc_search"}` (confidence 없음)
   - 신규: confidence < 0.75면 `router_node`에서 `route="clarify"` 반환

3. **clarify_node** (`app/graph/nodes/clarify.py` 신규):
   ```python
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
       route = _CLARIFY_OPTIONS.get(label, "doc_search")
       return {
           "route": route,
           "tool_input": question if route == "agent" else "",
       }
   ```
   - `interrupt()` payload는 message + options 형식 (UI 렌더러 재사용)
   - resume 값은 사용자 선택지 레이블 (한글) → 내부 route로 맵핑
   - KeyError 방어: 예상치 못한 선택지는 "doc_search"로 기본값 처리

4. **라우팅 엣지** (`app/graph/edges.py`):
   ```python
   def route_after_router(state: dict) -> str:
       route = state.get("route")
       if route == "clarify":
           return "clarify"
       elif route == "doc_search":
           return "doc_search_node"
       else:  # "agent"
           return "capability_router"
   ```

5. **그래프 배선** (`app/graph/builder.py`):
   ```
   router_node
       ├─→ [route="doc_search"] → doc_search_node
       ├─→ [route="agent"] → capability_router
       └─→ [route="clarify"] → clarify_node
                                    ↓
                          (user choice via interrupt)
                                    ↓
                          route_after_router 분기
                                    ├─→ doc_search_node
                                    └─→ capability_router
   ```

## Consequences

- **HITL 공식 범위 확장**: interrupt() 사용이 "agent 도구 호출 경로 + 라우터 분기 모호성 해소"로 명시됨
- **checkpointer**: 기존 `MemorySaver` 전역 적용이므로 추가 작업 없음. 모든 interrupt는 자동 session 저장
- **UI**: `interrupt()` payload 구조 (message + actions/options + type 필드) 동형 → 기존 `ConfirmDialog` 렌더러 확장으로 처리 가능 (신규 `ClarifyDialog` 또는 조건부 렌더링)
- **성능**: 확신도 < 0.75인 경우만 clarify 경로 진입 → 대다수 확실한 쿼리는 기존 대로 고속 처리
- **기존 동작**: doc_search/agent 확신도 ≥ 0.75인 경우는 기존 대로 직진. 호환성 유지

## 관련 ADR

- [ADR-0027](ADR-0027-write-human-in-the-loop.md) — HITL 원형 (confirm_node, MemorySaver)
- [ADR-0030](ADR-0030-interrupt-web-ui.md) — interrupt() 프론트 렌더링
- [ADR-0031](ADR-0031-router-agent-naming-clarify.md) — 라우터·에이전트 명명 표준
- [ADR-0033](ADR-0033-terminology-naming-deadcode-cleanup.md) — 외부 경계 명명 (route 필드)
