# 용어 정합 + 유령 코드 제거 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ADR-0023 이후 그래프에서 분리된 유령 SQL 코드를 제거하고, 라우팅 라벨 비일관과 외부 문서의 옛 용어(`tool_call`)를 표준(`agent`)으로 정합한다.

**Architecture:** 캡슐화 원칙(외부=role, 내부=how 허용) 아래 ① 내부 dead code 삭제 ② 라우팅 라벨 정렬 ③ 외부 문서 교정. 외부 스키마(`AuditRecord`, FGA `capability:sql`)와 `core/`는 불변 → DB 마이그레이션 없음.

**Tech Stack:** Python 3.11, LangGraph, pytest. cwd = `backend/`, 인터프리터 = `.venv/bin/python`.

---

## 작업 전 확인

모든 명령은 `backend/` 디렉토리에서 실행한다. 브랜치는 이미 `feat/terminology-cleanup`.

```bash
git branch --show-current   # feat/terminology-cleanup 이어야 함
```

---

### Task 1: 유령 SQL 노드 5개 + 전용 테스트 삭제

이 노드들은 `builder.py`의 `add_node`로 등록되지 않아 그래프에서 도달 불가하다 (검증 완료). `core.sql.gate`/`core.sql.risk`는 `tool_gate_node`가 사용하므로 **건드리지 않는다**.

**Files:**
- Delete: `app/graph/nodes/sql_generate.py`, `app/graph/nodes/sql_execute.py`, `app/graph/nodes/sql_reject.py`, `app/graph/nodes/classify_risk.py`, `app/graph/nodes/tool_executor.py`
- Delete: `tests/app/graph/nodes/test_sql_generate.py`, `tests/app/graph/nodes/test_sql_execute.py`, `tests/app/graph/nodes/test_sql_reject.py`, `tests/app/graph/nodes/test_classify_risk.py`, `tests/app/graph/nodes/test_tool_executor.py`

- [ ] **Step 1: 노드·테스트 파일 삭제**

```bash
git rm app/graph/nodes/sql_generate.py app/graph/nodes/sql_execute.py \
       app/graph/nodes/sql_reject.py app/graph/nodes/classify_risk.py \
       app/graph/nodes/tool_executor.py \
       tests/app/graph/nodes/test_sql_generate.py \
       tests/app/graph/nodes/test_sql_execute.py \
       tests/app/graph/nodes/test_sql_reject.py \
       tests/app/graph/nodes/test_classify_risk.py \
       tests/app/graph/nodes/test_tool_executor.py
```

- [ ] **Step 2: 잔존 참조가 없는지 확인**

Run:
```bash
grep -rn "sql_generate_node\|sql_execute_node\|sql_reject_node\|classify_risk_node\|tool_executor_node" app tests scripts
```
Expected: 결과 없음 (exit 1). 만약 `app/graph/nodes/__init__.py` 등에서 import가 잡히면 그 줄도 제거한다.

- [ ] **Step 3: 전체 테스트 통과 확인**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (삭제된 노드 테스트만 사라지고 나머지 그린). `edges.py`의 `route_after_gate/confirm`은 아직 살아있으므로 `test_edges.py`는 통과한다.

- [ ] **Step 4: 커밋**

```bash
git commit -m "refactor(graph): ADR-0023 이후 미연결 SQL 서브루틴 노드 제거"
```

---

### Task 2: `edges.py`의 죽은 라우팅 함수 제거

`route_after_gate`/`route_after_confirm`은 그래프에 등록되지 않으며, 더 이상 존재하지 않는 노드 `"sql_execute"`/`"sql_reject"`를 반환한다.

**Files:**
- Modify: `app/graph/edges.py` (함수 2개 제거)
- Modify: `tests/app/graph/test_edges.py` (import·테스트 블록 정리)

- [ ] **Step 1: `edges.py`에서 두 함수 제거**

`app/graph/edges.py`에서 아래 두 함수 정의 전체를 삭제한다 (현재 54–74행):

```python
def route_after_gate(state: dict) -> str:
    """Route based on the identity×risk gate decision (ADR-0016, 0027).

    Returns:
        "sql_execute" for ALLOW, "confirm" for JUSTIFY_AND_APPROVE, "sql_reject" for DENY.
    """
    decision = state["gate_decision"]
    if decision == "ALLOW":
        return "sql_execute"
    if decision == "JUSTIFY_AND_APPROVE":
        return "confirm"
    return "sql_reject"


def route_after_confirm(state: dict) -> str:
    """Route after JUSTIFY_AND_APPROVE justification (ADR-0027).

    Returns:
        "sql_execute" if a justification was given, "sql_reject" otherwise (no reason).
    """
    return "sql_execute" if state["confirmed"] else "sql_reject"
```

삭제 후 `route_after_router` 다음에 `route_after_agent`가 바로 오도록 한다.

- [ ] **Step 2: `test_edges.py` import에서 두 함수 제거**

`tests/app/graph/test_edges.py:2`를 아래로 교체:

```python
from app.graph.edges import route_after_grade, route_after_hallucination, route_after_router, route_after_agent, route_after_tool_gate
```

- [ ] **Step 3: `test_edges.py`의 죽은 테스트 블록 삭제**

아래 두 블록(현재 81–102행) 전체를 삭제한다:

```python
# ─── route_after_confirm (SQL 게이트 JUSTIFY_AND_APPROVE 전용) ───

def test_route_after_confirm_executes_when_confirmed():
    assert route_after_confirm({"confirmed": True}) == "sql_execute"


def test_route_after_confirm_rejects_when_denied():
    assert route_after_confirm({"confirmed": False}) == "sql_reject"


# ─── route_after_gate (ADR-0016 3-state, ADR-0027 개정) ───

def test_route_after_gate_allow_executes():
    assert route_after_gate({"gate_decision": "ALLOW"}) == "sql_execute"


def test_route_after_gate_justify_confirms():
    assert route_after_gate({"gate_decision": "JUSTIFY_AND_APPROVE"}) == "confirm"


def test_route_after_gate_deny_rejects():
    assert route_after_gate({"gate_decision": "DENY"}) == "sql_reject"
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/test_edges.py -q`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add app/graph/edges.py tests/app/graph/test_edges.py
git commit -m "refactor(graph): 미연결 라우팅 함수 route_after_gate/confirm 제거"
```

---

### Task 3: `AgentState`의 죽은 SQL 필드 제거

`generated_sql / sql_risk / gate_decision`(state 필드)은 어떤 활성 노드도 읽지 않는다. 감사 로그는 `PendingToolCall`에서 값을 취한다. **`AuditRecord`의 동명 필드는 외부 스키마이므로 유지** (`tool_gate.py`/`justify_execute.py`의 `AuditRecord(generated_sql=...)` 키워드 인자는 그대로 둔다).

**Files:**
- Modify: `app/graph/state.py:35-37` (필드 3개 제거)
- Modify: `app/graph/builder.py` (초기화 2곳)
- Modify: `tests/app/graph/test_state.py` (단언 갱신)
- Modify: `tests/app/graph/test_builder.py:75-77` (초기화 제거)

- [ ] **Step 1: `state.py`에서 죽은 필드 3줄 제거**

`app/graph/state.py`에서 아래 세 줄(35–37행)을 삭제:

```python
    generated_sql: str           # SQL 생성 노드가 채움 (ADR-0016)
    sql_risk: str                # 위험도 분류 노드가 채움 (ADR-0017)
    gate_decision: str           # 신원×위험도 게이트 결정 ALLOW/DENY/JUSTIFY_AND_APPROVE (ADR-0016, 0027)
```

`justification: str` 이하는 유지된다.

- [ ] **Step 2: `builder.py`의 두 초기화 블록에서 제거**

`app/graph/builder.py`의 `answer_question`(205–207행)과 `stream_answer`(262–264행) 두 곳 모두에서 아래 세 줄을 삭제:

```python
        "generated_sql": "",
        "sql_risk": "",
        "gate_decision": "",
```

(`stream_answer` 쪽은 들여쓰기가 한 단계 더 깊다 — 해당 블록의 동일 키 3줄을 제거한다.)

- [ ] **Step 3: `test_state.py`의 SQL 게이트 필드 테스트 갱신**

`tests/app/graph/test_state.py`의 `test_agent_state_has_sql_gate_fields`(61–66행)를 아래로 교체 (죽은 필드 단언 제거, `justification`만 남김):

```python
def test_agent_state_has_justification_field():
    hints = get_type_hints(AgentState, include_extras=True)
    assert "justification" in hints   # ADR-0027
```

- [ ] **Step 4: `test_builder.py`의 헬퍼 초기화에서 제거**

`tests/app/graph/test_builder.py`의 `_make_initial_state`(75–77행)에서 아래 세 줄을 삭제:

```python
        "generated_sql": "",
        "sql_risk": "",
        "gate_decision": "",
```

- [ ] **Step 5: 잔존 참조 확인**

Run:
```bash
grep -rn "\"generated_sql\"\|\"sql_risk\"\|state\[.gate_decision.\]\|state\.get(.gate_decision" app tests
```
Expected: `app/graph/nodes/` 및 `tests/` 에서 결과 없음. (`tool_gate.py`/`justify_execute.py`의 `generated_sql=`, `sql_risk=`, `gate_decision=` **키워드 인자**와 `AuditRecord` 관련 `tests/core/...`는 매칭되지 않아야 정상 — 매칭되면 그건 AuditRecord 인자이므로 건드리지 말 것)

- [ ] **Step 6: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/ -q`
Expected: PASS

- [ ] **Step 7: 커밋**

```bash
git add app/graph/state.py app/graph/builder.py tests/app/graph/test_state.py tests/app/graph/test_builder.py
git commit -m "refactor(state): AgentState의 미사용 SQL 게이트 필드 제거 (AuditRecord 스키마는 유지)"
```

---

### Task 4: 라우팅 라벨 정렬 — `agent_done` → `agent_answer`

`route_after_agent`가 한 분기는 노드명(`"tool_gate"`), 다른 분기는 상태명(`"agent_done"`)을 반환하는 비일관을 라벨=노드명으로 정렬한다 (ADR-0031 원칙②). 동작 불변.

**Files:**
- Modify: `tests/app/graph/test_edges.py` (기대값 먼저 갱신 — red)
- Modify: `app/graph/edges.py:83` (반환값)
- Modify: `app/graph/builder.py:121` (매핑 키)

- [ ] **Step 1: 테스트 기대값을 새 라벨로 갱신 (실패 유도)**

`tests/app/graph/test_edges.py`의 `test_route_after_agent_to_done_when_no_tool_calls`(112–114행)를 아래로 교체:

```python
def test_route_after_agent_to_answer_when_no_tool_calls():
    ai = AIMessage(content="최종 답변")
    assert route_after_agent({"agent_messages": [ai]}) == "agent_answer"
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/test_edges.py::test_route_after_agent_to_answer_when_no_tool_calls -q`
Expected: FAIL — `assert 'agent_done' == 'agent_answer'`

- [ ] **Step 3: `edges.py`의 반환값 정렬**

`app/graph/edges.py`의 `route_after_agent`에서 `"agent_done"` 두 곳(현재 83행의 삼항과 84행의 fallback)을 `"agent_answer"`로 교체:

```python
def route_after_agent(state: dict) -> str:
    """에이전트 응답에 도구 호출이 있으면 게이트로, 없으면 최종 답변 노드로 (ADR-0023, ADR-0031 라벨=노드명)."""
    messages = state.get("agent_messages") or []
    for m in reversed(messages):
        tool_calls = getattr(m, "tool_calls", None)
        if tool_calls is not None:
            return "tool_gate" if tool_calls else "agent_answer"
    return "agent_answer"
```

- [ ] **Step 4: `builder.py`의 매핑 키 정렬**

`app/graph/builder.py:121`의 매핑을 교체:

```python
        {"tool_gate": "tool_gate", "agent_answer": "agent_answer"},
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/test_edges.py tests/app/graph/test_builder.py -q`
Expected: PASS

- [ ] **Step 6: 커밋**

```bash
git add app/graph/edges.py app/graph/builder.py tests/app/graph/test_edges.py
git commit -m "refactor(graph): route_after_agent 라벨을 노드명 agent_answer로 정렬 (ADR-0031)"
```

---

### Task 5: 전체 회귀 검증

**Files:** 없음 (검증 전용)

- [ ] **Step 1: 전체 단위 테스트**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS, 0 errors. 실패 시 해당 Task로 돌아가 잔존 참조를 정리한다.

- [ ] **Step 2: eval 회귀 점수**

Run: `.venv/bin/python -m tests.eval.runner`
Expected: 활성 그래프 흐름이 불변이므로 직전 baseline과 동일 점수. 하락 시 원인을 기록하고 진행 여부를 보고한다.

> eval 러너 실행에 외부 API 키/DB가 필요해 로컬에서 돌릴 수 없으면, 그 사실과 함께 "그래프 토폴로지·노드 동작 불변"을 근거로 회귀 없음을 명시한다.

---

### Task 6: 외부 문서의 `tool_call` 잔재 교정

코드 표준은 `agent`다. 외부 독자용 문서를 현재 그래프 흐름에 맞춘다. `backend-internals.md:105`는 유령 노드 `tool_executor`도 참조하므로 현재 흐름으로 갱신한다.

**Files:**
- Modify: `backend/CLAUDE.md:18-19`
- Modify: `docs/architecture/backend-internals.md` (24, 50, 68, 105행)
- Modify: `docs/architecture/interview-questions-with-answers.md` (38, 41행)

- [ ] **Step 1: `backend/CLAUDE.md` 교정**

18–19행을 교체:

```markdown
- 라우터: `router_node` — `route` 필드로 doc_search/agent 분기 (`app/graph/nodes/router.py`)
- HITL: `interrupt()` — agent(도구 호출) 경로에만, `MemorySaver` checkpointer 필수 (`app/graph/nodes/confirm.py`)
```

- [ ] **Step 2: `backend-internals.md` 교정**

- 24행: `RT -->|tool_call| CF{confirm...}` → 라벨을 `agent`로, 목적지를 현재 흐름(`agent` 노드)로. 해당 다이어그램 구간을 현재 토폴로지 `RT -->|agent| AG[agent] --> TG{tool_gate}` 형태로 맞춘다 (다이어그램 전체 맥락을 보고 인접 노드와 일관되게 수정).
- 50행: `` `"doc_search" \| "tool_call"` `` → `` `"doc_search" \| "agent"` ``
- 68행: `route_after_router ... `tool_call` → confirm` → `` `agent` → agent ``
- 105행: "`tool_call` 경로의 `confirm_node`...`tool_executor` 진입 또는 END" → 현재 흐름으로: "`agent`(도구 호출) 경로에서 `tool_gate`가 JUSTIFY 판정 시 `confirm_node`가 `interrupt()`로 사용자 확인을 받고, 사유 입력 후 `justify_execute_node`가 실행한다."

> 실행 시 해당 다이어그램/표의 전후 맥락을 읽고, 현재 활성 노드(`agent`, `tool_gate`, `confirm`, `justify_execute`, `agent_answer`)와 일치하도록 수정한다. 옛 `sql_*` 노드 참조가 다이어그램에 더 있으면 함께 갱신한다.

- [ ] **Step 3: `interview-questions-with-answers.md` 교정**

- 38행: "`route`가 단순 질문을 `tool_call`/단순 경로로" → "`route`가 단순 질문을 `agent`/단순 경로로"
- 41행 제목: "Q8. HITL이 tool_call에만, doc_search는..." → "Q8. HITL이 agent(도구) 경로에만, doc_search는..."

- [ ] **Step 4: 잔존 확인**

Run:
```bash
grep -rn "tool_call" CLAUDE.md docs/architecture/
```
Expected: 결과 없음. (LangChain 표준어 `tool_calls`/`pending_tool_calls`가 코드 인용으로 남는 건 무방하나, 위 문서 파일에는 없어야 한다.)

- [ ] **Step 5: 커밋**

```bash
git add CLAUDE.md docs/architecture/backend-internals.md docs/architecture/interview-questions-with-answers.md
git commit -m "docs: 외부 문서의 옛 라벨 tool_call → agent 정합 (ADR-0031)"
```

---

### Task 7: ADR-0033 작성 + CLAUDE.md 갱신 + 인덱스 재생성

**Files:**
- Create: `docs/superpowers/decisions/ADR-0033-terminology-naming-deadcode-cleanup.md`
- Modify: `backend/CLAUDE.md` (FGA/아키텍처 섹션에 명명 원칙 한 줄, ADR 참조)
- Regenerate: `docs/superpowers/decisions/README.md`

- [ ] **Step 1: ADR-0033 작성**

`docs/superpowers/decisions/ADR-0033-terminology-naming-deadcode-cleanup.md`:

```markdown
# ADR-0033: 캡슐화 기반 명명 표준 + 유령 SQL 코드 제거

> **Status**: 🟢 적용완료

## Context

프로젝트 전반의 용어를 조사한 결과, 코드는 ADR-0031로 `agent` 라벨에 정착했으나
(1) ADR-0023에서 ReAct 루프로 대체된 고정 SQL 흐름의 노드·함수·state 필드가 그래프에
미연결인 채 잔존하고, (2) `route_after_agent`가 노드명과 상태명을 섞어 반환하며,
(3) 외부 문서가 옛 라벨 `tool_call`에 머물러 있었다.

## Decision

**명명 표준 — 캡슐화**: 외부 경계에 노출되는 이름은 역할(role)로, 내부 구현 디테일은
how(메커니즘)를 허용한다. 이 기준에서 `citations`(내부)↔`sources`(외부 API),
노드명 `multi_query`/`tool_gate`(내부), `AuditRecord`/`capability:sql`(외부 스키마)은
모두 정당하므로 유지한다.

**정리 범위(최소안)**:
1. 미연결 SQL 노드 5개(`sql_generate/execute/reject`, `classify_risk`, `tool_executor`)와
   라우팅 함수 `route_after_gate/confirm`, `AgentState`의 죽은 필드
   `generated_sql/sql_risk/gate_decision` 제거.
2. `route_after_agent` 반환 라벨 `agent_done` → `agent_answer`로 정렬(라벨=노드명).
3. 외부 문서(`CLAUDE.md`, `backend-internals.md`, `interview-questions`)의 `tool_call` 교정.

**범위 밖**: 외부 스키마 재명명(`AuditRecord` 필드, FGA `capability:sql`)은 마이그레이션
비용으로 보류. `core/`는 규칙 5에 따라 불변. 레거시 plan 문서는 역사 기록으로 보존.

## Consequences

- 그래프 토폴로지·노드 동작 불변 → 기능 회귀 없음. DB 마이그레이션 없음.
- dead code 제거로 용어 혼란 표면적이 감소하고, 라벨=노드명 일관성이 확보된다.
- 후속 과제: 외부 감사 스키마(`generated_sql/sql_risk`)의 도구 불가지 재명명(별도 ADR).

## 관련

- ADR-0023(tool_call 에이전트화), ADR-0031(라우터 agent 라벨)
- Spec: `docs/superpowers/specs/2026-06-04-terminology-deadcode-cleanup-design.md`
```

- [ ] **Step 2: `backend/CLAUDE.md` 아키텍처 섹션에 명명 원칙·ADR 참조 추가**

"핵심 아키텍처 결정" 섹션 끝에 한 줄 추가:

```markdown
- 명명 원칙: 외부 경계 노출 이름은 역할(role), 내부 구현은 how 허용(캡슐화). 상세: ADR-0033.
```

- [ ] **Step 3: ADR 인덱스 재생성**

Run: `.venv/bin/python -m scripts.gen_adr_index`
Expected: `docs/superpowers/decisions/README.md`에 ADR-0033 행이 추가됨.

- [ ] **Step 4: 인덱스 갱신 확인**

Run: `grep -n "0033" docs/superpowers/decisions/README.md`
Expected: ADR-0033 행 출력.

- [ ] **Step 5: 커밋**

```bash
git add docs/superpowers/decisions/ADR-0033-terminology-naming-deadcode-cleanup.md docs/superpowers/decisions/README.md CLAUDE.md
git commit -m "docs(adr): ADR-0033 캡슐화 명명 표준 + 유령 코드 제거 기록"
```

---

### Task 8: 최종 검증 + PR

- [ ] **Step 1: 전체 테스트 재확인**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS

- [ ] **Step 2: 푸시 + PR 생성**

```bash
git push -u origin feat/terminology-cleanup
gh pr create --title "용어 정합 + 유령 SQL 코드 제거 (ADR-0033)" --body "$(cat <<'EOF'
## 요약
캡슐화 명명 원칙 아래 ① 미연결 SQL 유령 코드 제거 ② 라우팅 라벨 정렬(agent_done→agent_answer) ③ 외부 문서 tool_call→agent 교정.

## DoD
- [x] 단위 테스트 통과
- [x] eval 회귀 확인 (그래프 흐름 불변)
- [x] ADR-0033 작성 + CLAUDE.md 갱신

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review

**Spec coverage:**
- 변경 1(유령 코드) → Task 1·2·3 ✅
- 변경 2(라벨 정렬) → Task 4 ✅
- 변경 3(문서 교정) → Task 6 ✅
- DoD(테스트·eval·ADR·CLAUDE.md) → Task 5·7·8 ✅
- "절대 유지" 항목(`core.sql.gate`, `AuditRecord`) → Task 1·3의 명시적 가드 + grep 검증 ✅

**Placeholder scan:** 모든 코드 step에 실제 코드/명령 포함. 문서 교정(Task 6)은 다이어그램 맥락 의존이라 "전후 맥락 확인" 지시 + 정확한 대상 행·교체문을 제시. 

**Type consistency:** 제거 대상 식별자(`route_after_gate/confirm`, `generated_sql/sql_risk/gate_decision` 필드, `agent_done`)가 모든 Task에서 동일하게 참조됨. 유지 대상(함수 `gate_decision`, `AuditRecord` 필드)과 제거 대상(state 필드)을 Task 3에서 명시적으로 구분.
