# 라우터 route 명명(agent) + 게이트 도구 단일인자 처리 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 권한부여 질문이 안정적으로 도구 경로로 라우팅되고, 게이트 도구가 모델 인자를 올바로 읽어 권한 JUSTIFY interrupt가 실제로 동작하게 한다.

**Architecture:** (A) 라우터 route 라벨 `tool_call`→`agent` 리네임 + ROUTER_PROMPT를 권한관리까지 포함하도록 확장(2-way 구조·ReAct 뒷단 무변경). (B) SQL·권한 게이트 도구가 단일 NL 입력을 `__arg1` 포함 견고하게 추출하도록 공용 헬퍼로 수정.

**Tech Stack:** Python 3.11+, LangGraph, langchain-core Tool, pytest. 작업 디렉토리 **`backend/`**. 테스트: `.venv/bin/python -m pytest`.

**설계 출처:** `docs/superpowers/specs/2026-06-03-router-rename-agent-tool-args-design.md`

**핵심 사실(검증 완료 2026-06-03):**
- 모델은 단일입력 Tool 인자를 `{'__arg1': '...'}`로 넘긴다(라이브 invoke 확인). 두 핸들러는 `args["question"]`/`args["instruction"]`로 읽어 `KeyError`.
- `generate.py:13`은 `route == "doc_search"`만 검사 → 리네임은 generate에 영향 없음.
- `route_after_router`(`edges.py:48-51`)는 `state["route"]`를 그대로 반환, multi_query 특례는 doc_search 전용 → 로직 변경 불필요.
- route 라벨 `tool_call`이 박힌 곳(리네임 대상): 코드 `router.py`/`state.py`/`builder.py`/`prompts.py`, 테스트 `test_state.py`/`test_edges.py`/`test_router.py`/`test_router_edge_cases.py`/`test_generate.py`/`test_builder.py`/`test_prompts.py`.
- **불변**(이름만 유사, route와 무관): `tool_call_id`, `tool_calls`, `pending_tool_calls`, 테스트 헬퍼 함수명 `_tool_call_msg`/`_perm_tool_call_msg`.

---

## File Structure

| 파일 | 책임 | 변경 |
|------|------|------|
| `app/graph/tools/_args.py` | 단일 NL 입력 추출 | **신규** `single_text_arg` |
| `app/graph/tools/sql_tool.py` | SQL 도구 plan | `:47` 헬퍼 사용 |
| `app/graph/tools/permission_tool.py` | 권한 도구 plan | `:37` 헬퍼 사용 |
| `app/graph/nodes/router.py` | route 분류 | `_VALID_ROUTES`·판정에 `agent` |
| `app/graph/state.py` | AgentState | `route` Literal 갱신 |
| `app/graph/builder.py` | 그래프 배선 | 조건부 엣지 키 |
| `app/graph/prompts.py` | ROUTER_PROMPT | 라벨 리네임 + 권한 포함 확장 |
| `tests/...` (7개 파일) | 회귀 | route 값·프롬프트 assert 갱신 |
| `docs/.../decisions/ADR-0031,0032` | 결정 기록 | **신규** |

---

## Task 1: 게이트 도구 단일 인자 헬퍼 + 핸들러 수정 (ADR-0032)

**Files:**
- Create: `app/graph/tools/_args.py`, `tests/app/graph/tools/test_args.py`
- Modify: `app/graph/tools/sql_tool.py:47`, `app/graph/tools/permission_tool.py:37`
- Test(확장): `tests/app/graph/tools/test_sql_tool.py`, `tests/app/graph/tools/test_permission_tool.py`

- [ ] **Step 1: 헬퍼 실패 테스트 작성**

`tests/app/graph/tools/test_args.py` 생성:

```python
from app.graph.tools._args import single_text_arg


def test_prefers_named_key():
    assert single_text_arg({"question": "Q", "__arg1": "X"}, prefer="question") == "Q"


def test_falls_back_to_arg1_when_named_missing():
    assert single_text_arg({"__arg1": "전직원 급여"}, prefer="question") == "전직원 급여"


def test_falls_back_to_single_value():
    assert single_text_arg({"weird_key": "값"}, prefer="question") == "값"


def test_returns_empty_for_empty_args():
    assert single_text_arg({}, prefer="instruction") == ""
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/tools/test_args.py -q`
Expected: FAIL (`ModuleNotFoundError: app.graph.tools._args`)

- [ ] **Step 3: 헬퍼 구현**

`app/graph/tools/_args.py` 생성:

```python
"""게이트 도구 인자 추출 (ADR-0032).

bind_tools가 단일 문자열 입력 Tool의 인자를 '__arg1'로 넘기는 레거시 형태를 흡수한다.
named 키(prefer) → '__arg1' → 단일 값 → '' 순으로 폴백한다.
"""


def single_text_arg(args: dict, *, prefer: str) -> str:
    if prefer in args:
        return args[prefer]
    if "__arg1" in args:
        return args["__arg1"]
    if len(args) == 1:
        return next(iter(args.values()))
    return ""
```

- [ ] **Step 4: 헬퍼 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/tools/test_args.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: sql_tool 실패 테스트 추가**

`tests/app/graph/tools/test_sql_tool.py`에 추가:

```python
def test_plan_accepts_arg1_key():
    """bind_tools가 넘기는 {'__arg1': ...} 형태에서도 NL 질문을 추출한다 (ADR-0032)."""
    llm = MagicMock()
    llm.complete.side_effect = ["SELECT name FROM business.employees", "no"]
    h = SqlToolHandler(llm=llm, sql_pool=MagicMock())
    planned, risk = h.plan({"__arg1": "엔지니어링 부서원 이름"})
    assert "business.employees" in planned
    assert risk == "select"
```

- [ ] **Step 6: permission_tool 실패 테스트 추가**

`tests/app/graph/tools/test_permission_tool.py`에 추가:

```python
def test_plan_accepts_arg1_key():
    """bind_tools가 넘기는 {'__arg1': ...} 형태에서도 instruction을 추출한다 (ADR-0032)."""
    handler = PermissionToolHandler(
        llm=_llm('{"action":"grant","subject":"user:user-alice","relation":"member","object":"department:engineering"}'),
        fga_client=MagicMock(), validator=_validator(),
    )
    planned, risk = handler.plan({"__arg1": "alice를 engineering에 추가"})
    assert risk == RISK_GRANT
    assert planned == "grant user:user-alice member department:engineering"
```

- [ ] **Step 7: 두 도구 테스트 실패 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/tools/test_sql_tool.py::test_plan_accepts_arg1_key tests/app/graph/tools/test_permission_tool.py::test_plan_accepts_arg1_key -q`
Expected: FAIL (`KeyError: 'question'` / `KeyError: 'instruction'`)

- [ ] **Step 8: 핸들러 수정 — sql_tool**

`app/graph/tools/sql_tool.py` 상단 import에 추가(기존 `from app.graph.nodes.sql_generate import _strip_code_fence` 아래):

```python
from app.graph.tools._args import single_text_arg
```

`app/graph/tools/sql_tool.py:47` `question = args["question"]`를 다음으로 교체:

```python
        question = single_text_arg(args, prefer="question")
```

- [ ] **Step 9: 핸들러 수정 — permission_tool**

`app/graph/tools/permission_tool.py` 상단 import에 추가(기존 import 블록 끝):

```python
from app.graph.tools._args import single_text_arg
```

`app/graph/tools/permission_tool.py:37` `instruction = args["instruction"]`를 다음으로 교체:

```python
        instruction = single_text_arg(args, prefer="instruction")
```

- [ ] **Step 10: 도구 테스트 전체 통과 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/tools/ -q`
Expected: PASS (기존 + 신규 2개, 회귀 0)

- [ ] **Step 11: Commit**

```bash
git add app/graph/tools/_args.py tests/app/graph/tools/test_args.py app/graph/tools/sql_tool.py app/graph/tools/permission_tool.py tests/app/graph/tools/test_sql_tool.py tests/app/graph/tools/test_permission_tool.py
git commit -m "fix(tools): 게이트 도구 단일입력 __arg1 추출 — KeyError 해소 (ADR-0032)"
```

---

## Task 2: route 라벨 `tool_call` → `agent` 리네임 (app + 테스트)

**Files:**
- Modify: `app/graph/nodes/router.py`, `app/graph/state.py`, `app/graph/builder.py`, `app/graph/prompts.py`
- Test(갱신): `tests/app/graph/test_state.py`, `tests/app/graph/test_edges.py`, `tests/app/graph/nodes/test_router.py`, `tests/app/graph/nodes/test_router_edge_cases.py`, `tests/app/graph/nodes/test_generate.py`, `tests/app/graph/test_builder.py`

이 task는 라벨만 바꾼다(의미 확장은 Task 3). 코드와 그 코드를 검증하는 테스트를 같은 커밋에서 함께 바꿔 항상 green을 유지한다.

- [ ] **Step 1: 테스트 라벨 갱신 (실패→통과 동시 전환이므로 코드와 함께 진행)**

다음 테스트들의 **route 값 문자열** `"tool_call"`(및 `"  tool_call  "`)을 `"agent"`로, route 단언 `== "tool_call"`을 `== "agent"`로 바꾼다. 헬퍼 함수명 `_tool_call_msg`/`_perm_tool_call_msg`와 `tool_calls`/`pending_tool_calls`/`tool_call_id`는 **건드리지 않는다**.

`tests/app/graph/test_state.py:47`:
```python
        "route": "agent",
```

`tests/app/graph/test_edges.py:61-62`를 교체:
```python
def test_route_after_router_returns_agent():
    assert route_after_router({"route": "agent"}) == "agent"
```

`tests/app/graph/nodes/test_router.py:16-23`를 교체:
```python
def test_router_sets_agent_route_and_tool_input():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "agent"

    result = router_node({"rewritten_question": "회의실 예약해줘"}, llm=mock_llm)

    assert result["route"] == "agent"
    assert result["tool_input"] == "회의실 예약해줘"
```

`tests/app/graph/nodes/test_router_edge_cases.py` `test_router_strips_whitespace`(14~18행)를 교체:
```python
def test_router_strips_whitespace():
    """Test that router strips whitespace from LLM output"""
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "  agent  "
    result = router_node({"rewritten_question": "테스트"}, llm=mock_llm)
    assert result["route"] == "agent"
```

`tests/app/graph/nodes/test_generate.py:188` 함수명과 `:197` route 값:
```python
async def test_generate_node_no_notice_for_agent_route():
```
```python
        "route": "agent",
```

`tests/app/graph/test_builder.py`: 라우터 mock 응답 문자열 `"tool_call"`을 `"agent"`로 바꾼다(주석 `# router`가 붙은 줄들: 143, 170, 196, 225, 254, 281, 646, 710, 739, 768). 예시(각 위치 동일 패턴):
```python
        "agent",                                            # router
```

- [ ] **Step 2: 갱신 전 테스트가 실패하는지 확인(라벨 불일치)**

Run: `.venv/bin/python -m pytest tests/app/graph/nodes/test_router.py tests/app/graph/test_edges.py -q`
Expected: 아직 코드 미변경이면 위에서 바꾼 테스트가 FAIL(라우터가 `_VALID_ROUTES`에 없는 `"agent"`를 doc_search로 폴백). 이 실패는 다음 스텝의 코드 변경으로 해소된다.

- [ ] **Step 3: router.py 수정**

`app/graph/nodes/router.py:4`:
```python
_VALID_ROUTES = {"doc_search", "agent"}
```
`app/graph/nodes/router.py:18`:
```python
    tool_input = state["rewritten_question"] if route == "agent" else ""
```

- [ ] **Step 4: state.py 수정**

`app/graph/state.py:22`:
```python
    route: Literal["doc_search", "agent"]
```

- [ ] **Step 5: builder.py 수정**

`app/graph/builder.py:103` 매핑 키 교체:
```python
            "agent": "agent",
```
`app/graph/builder.py:117` 주석 교체:
```python
    # agent → 게이트된 에이전트 루프 (ADR-0023)
```

- [ ] **Step 6: prompts.py 라벨 리네임 (의미 확장 아님)**

`app/graph/prompts.py` ROUTER_PROMPT 내 `tool_call` 토큰을 `agent`로 바꾼다(라벨만):
- 66행 `- tool_call: 아래 업무 DB...` → `- agent: 아래 업무 DB...`
- 68행 `업무 DB 스키마(tool_call로 답할 수 있는 범위):` → `업무 DB 스키마(agent로 답할 수 있는 범위):`
- 72행 `- 그렇다 → tool_call` → `- 그렇다 → agent`
- 74행 `(tool_call은 비용·위험이 커` → `(agent은 비용·위험이 커`
- 78행 `→ tool_call:none` → `→ agent:none`
- 80행 `→ tool_call:none` → `→ agent:none`
- 87행 `예시: doc_search:none, doc_search:multi_query, tool_call:none` → `예시: doc_search:none, doc_search:multi_query, agent:none`

- [ ] **Step 7: 리네임 후 전체 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/app/graph -q`
Expected: PASS (전부). 특히 router/edges/builder/state/generate/prompts 회귀 0.

- [ ] **Step 8: 잔존 라벨 점검**

Run: `grep -rn 'tool_call' app/graph/nodes/router.py app/graph/state.py app/graph/builder.py app/graph/prompts.py | grep -v 'tool_call_id\|tool_calls\|pending_tool_calls'`
Expected: 출력 없음(빈 결과). route 라벨 `tool_call` 잔존 0.

- [ ] **Step 9: Commit**

```bash
git add app/graph/nodes/router.py app/graph/state.py app/graph/builder.py app/graph/prompts.py tests/app/graph/test_state.py tests/app/graph/test_edges.py tests/app/graph/nodes/test_router.py tests/app/graph/nodes/test_router_edge_cases.py tests/app/graph/nodes/test_generate.py tests/app/graph/test_builder.py
git commit -m "refactor(router): route 라벨 tool_call→agent 리네임 (ADR-0031)"
```

---

## Task 3: ROUTER_PROMPT 권한관리 포함 확장 + 프롬프트 테스트 (ADR-0031)

**Files:**
- Modify: `app/graph/prompts.py` (ROUTER_PROMPT 본문)
- Test(갱신): `tests/app/graph/test_prompts.py`

`agent` 분기가 "업무 DB 조회" + "권한 관리"를 모두 포괄하도록 의미를 넓힌다. 이게 권한 질문을 도구 경로로 안정 라우팅하는 실제 수정이다.

- [ ] **Step 1: 프롬프트 테스트 갱신/추가 (실패 유도)**

`tests/app/graph/test_prompts.py`의 `test_router_prompt_criterion_is_data_source_not_verbs`(48~52행)를 교체:

```python
def test_router_prompt_criterion_covers_docs_vs_tools_not_verbs():
    """판정 축이 동작 동사가 아니라 '문서 서술 vs 도구 처리'여야 한다."""
    assert "문서 서술로 답되는가" in ROUTER_PROMPT
    # 옛 동사 나열("예약, 조회, 실행, 전송 등 동작")이 제거되어야 한다.
    assert "예약, 조회, 실행, 전송" not in ROUTER_PROMPT


def test_router_prompt_includes_permission_management():
    """agent 분기가 권한 관리도 포괄함이 명시되어야 한다 (ADR-0031)."""
    assert "권한 관리" in ROUTER_PROMPT
    assert "agent:none" in ROUTER_PROMPT
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/test_prompts.py -q`
Expected: FAIL (`문서 서술로 답되는가`·`권한 관리` 미존재)

- [ ] **Step 3: ROUTER_PROMPT 본문 확장**

`app/graph/prompts.py`의 ROUTER_PROMPT에서 분기 설명·판정 기준·few-shot을 다음과 같이 교체한다.

분기 설명(현재 65~66행 두 줄)을:
```
- doc_search: 정책·규정·절차·가이드 등 사내 문서에 서술된 내용으로 답하는 질문
- agent: 도구로 처리하는 질문 — 업무 DB 테이블 값 조회·집계, 또는 사내 권한 관리(부서 멤버십·폴더 접근·SQL 실행 권한의 부여/회수)
```

판정 기준(현재 71~74행)을:
```
판정 기준: "이 질문이 사내 문서 서술로 답되는가, 아니면 도구로 처리해야 하는가?"
- 업무 DB 테이블 값으로 답된다(조회·집계), 또는 사내 권한을 변경/조회해야 한다 → agent
- 정책·규정·방침·방법 등 문서 서술이 필요하다 → doc_search
- 모호하면 doc_search로 답한다 (agent은 비용·위험이 커 불확실할 땐 doc_search로 기운다)
```

경계 예시(현재 76~80행)에 권한 예시 2개를 추가(기존 4개 유지 + 아래 2줄):
```
- "alice를 engineering 부서에 추가해줘" → agent:none (권한 변경 = 도구)
- "finance 폴더 접근 권한을 회수해줘" → agent:none (권한 변경 = 도구)
```

> 주의: `_BUSINESS_SCHEMA`(`{schema}` 치환)와 `business.employees`/`business.sales` 문구는 유지한다(기존 `test_router_prompt_exposes_business_schema`가 검증). "모호하면 doc_search" 문구도 유지.

- [ ] **Step 4: 프롬프트 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/test_prompts.py -q`
Expected: PASS (신규 2개 + 기존 schema/fewshot/fallback 회귀 0)

- [ ] **Step 5: 전체 테스트 회귀 확인**

Run: `.venv/bin/python -m pytest tests/app/graph -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/graph/prompts.py tests/app/graph/test_prompts.py
git commit -m "feat(router): ROUTER_PROMPT에 권한관리(agent) 포함 — 권한 질문 라우팅 안정화 (ADR-0031)"
```

---

## Task 4: 잔존 점검 + ADR-0031/0032 작성 + 인덱스 재생성

**Files:**
- Create: `docs/superpowers/decisions/ADR-0031-router-agent-label-permission-routing.md`, `docs/superpowers/decisions/ADR-0032-gated-tool-single-arg.md`
- Regenerate: `docs/superpowers/decisions/README.md`

- [ ] **Step 1: 전역 잔존 라벨 점검**

Run: `grep -rn 'tool_call' app/ tests/ --include='*.py' | grep -v 'tool_call_id\|tool_calls\|pending_tool_calls\|_tool_call_msg\|_perm_tool_call_msg'`
Expected: 출력 없음(route 라벨 `tool_call` 잔존 0). 남으면 해당 위치를 `agent`로 교정 후 재실행.

- [ ] **Step 2: ADR-0031 작성**

`docs/superpowers/decisions/ADR-0031-router-agent-label-permission-routing.md` 생성:

```markdown
# ADR-0031: 라우터 route 라벨 `agent` 명명 + 권한관리 라우팅 포함

> **Status**: 🟢 적용완료   <!-- 🟢 적용완료 · 🔵 승인됨 · ⚪ 제안됨 · 🟡 보류 · 🟣 대체됨 · ⚫ 폐기 -->

**Date**: 2026-06-03
**Context**: ROUTER_PROMPT이 비문서 경로(`tool_call`)를 "업무 DB 조회"로만 정의해, SP2b(ADR-0029)로 추가된 권한관리(`manage_permission`) 질문이 도구 경로에 안정적으로 도달하지 못했다(라우터가 doc_search로 폴백). web JUSTIFY 카드(ADR-0030)가 실서비스에서 뜨지 않는 원인이었다.

## Decision
- 2-way 라우팅 유지(`doc_search` vs `agent`). 분기 뒤 ReAct 에이전트(ADR-0023)가 SQL/권한 도구를 선택하는 구조 보존.
- route 라벨 `tool_call` → `agent`로 명명. 도구 중립적이며 목적지 노드 `agent`와 정렬.
- ROUTER_PROMPT의 `agent` 분기를 "업무 DB 조회·집계 또는 사내 권한 관리"로 확장. 판정 기준을 "문서 서술 vs 도구 처리"로 재구성, 권한 few-shot 추가, "모호하면 doc_search" 편향 유지.

## 고려했으나 기각한 대안 — 에이전트-우선 단일 진입
라우터를 없애고 단일 ReAct 에이전트가 문서검색(도구화)·SQL·권한을 모두 도구 선택으로 처리. 기각: (1) doc_search의 Self-RAG 그래프(rewrite→multi_query→permission pre-filter→retrieve→grade→hallucination→retry)를 한 도구로 싸야 해 그래프 레벨 제어 상실, (2) 흔한 문서질문까지 ReAct 루프로 비용·지연 증가, (3) 결정성·디버깅 저하, (4) ADR-0022/0023 전제 뒤집음.

## Consequences
- 권한 질문이 `agent`로 안정 라우팅 → `manage_permission` → 게이트 → confirm(interrupt) → JUSTIFY 카드 동작.
- ADR-0022(데이터-원천 분류) 개정: 판정 축이 "테이블 값" → "문서 vs 도구"로 일반화.
- 도구 인자 결함은 ADR-0032에서 별도 해소(권한 JUSTIFY 동작에 함께 필요).

## 관련 ADR
- [[ADR-0022]] 라우터 분류 — 본 ADR이 개정
- [[ADR-0023]] tool_call ReAct 루프 — 보존, `agent` 라벨로 노드명 정렬
- [[ADR-0029]] manage_permission — 라우팅 도달 대상
- [[ADR-0030]] web JUSTIFY 카드 — 이 수정으로 실환경 동작
- [[ADR-0032]] 게이트 도구 단일인자 — 함께 필요
```

- [ ] **Step 3: ADR-0032 작성**

`docs/superpowers/decisions/ADR-0032-gated-tool-single-arg.md` 생성:

```markdown
# ADR-0032: 게이트 도구 단일 입력 인자(`__arg1`) 처리

> **Status**: 🟢 적용완료   <!-- 🟢 적용완료 · 🔵 승인됨 · ⚪ 제안됨 · 🟡 보류 · 🟣 대체됨 · ⚫ 폐기 -->

**Date**: 2026-06-03
**Context**: SQL·권한 게이트 도구는 `langchain_core.tools.Tool(func=lambda question: "")` / `lambda instruction: ""`로 정의된 단일 문자열 입력 레거시 Tool이다. `bind_tools`된 모델은 호출 인자를 `{'__arg1': '...'}`로 넘기는데, 두 핸들러의 `plan()`이 `args["question"]`/`args["instruction"]`로 읽어 `KeyError`로 크래시했다(`/chat/stream`에서 `{"type":"error","message":"'question'"}`). 이로 인해 SQL JUSTIFY·권한 JUSTIFY interrupt 경로가 게이트 전에 죽었다.

## Decision
- 공용 헬퍼 `app/graph/tools/_args.py::single_text_arg(args, *, prefer)` 도입. named 키(`prefer`) → `__arg1` → 단일 값 → `""` 순으로 폴백.
- `sql_tool.plan`/`permission_tool.plan`이 이 헬퍼로 단일 NL 입력을 추출. 도구 contract·게이트·실행 로직은 불변.

## Consequences
- 모델이 `__arg1`로 넘겨도 NL 입력을 안정적으로 추출 → 두 게이트 도구가 게이트·interrupt 경로까지 정상 진행.
- ADR-0031(라우팅)과 함께 권한 JUSTIFY가 end-to-end 동작.

## 관련 ADR
- [[ADR-0023]] 게이트된 도구 디스패치 — 이 도구들의 plan/execute 출처
- [[ADR-0029]] manage_permission — 동일 결함 보유, 함께 해소
- [[ADR-0031]] 라우터 agent 라벨 — 함께 권한 JUSTIFY 동작
```

- [ ] **Step 4: 인덱스 재생성**

Run: `.venv/bin/python -m scripts.gen_adr_index`
Expected: `decisions/README.md` 재생성, ADR-0031·0032 행 추가(🟢 적용완료)

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/decisions/ADR-0031-router-agent-label-permission-routing.md docs/superpowers/decisions/ADR-0032-gated-tool-single-arg.md docs/superpowers/decisions/README.md
git commit -m "docs(adr): ADR-0031 라우터 agent 라벨·권한 라우팅 + ADR-0032 게이트 도구 단일인자"
```

---

## Task 5: 라이브 수동 검증 + eval 회귀

자동 테스트로 단위 회귀는 커버되나, 권한 JUSTIFY end-to-end는 라이브로 확인한다.

- [ ] **Step 1: 서버 기동 (이미 떠 있으면 생략)**

```bash
# Docker(PostgreSQL+OpenFGA) 가동 확인
docker ps --format '{{.Names}}'
# 백엔드
.venv/bin/python -m uvicorn app.api.chat:app --port 8000
```

- [ ] **Step 2: 권한 질문 → interrupt 확인 (curl)**

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/auth/token -H 'Content-Type: application/json' -d '{"username":"admin","password":"admin123"}' | .venv/bin/python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
curl -s -N -X POST http://localhost:8000/chat/stream -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"question":"alice를 engineering 부서에 추가해줘","session_id":null}' --max-time 90 | grep -E '"type": "(interrupt|error|done)"'
```
Expected: `{"type": "interrupt", "actions": [{"tool": "manage_permission", "planned_action": "grant ..."}]}` 가 나오고 `error` 없음.

- [ ] **Step 3: web UI 수동 확인 (선택)**

web(`cd ../web && npm run dev`) → admin/admin123 로그인 → "alice를 engineering 부서에 추가해줘" → JUSTIFY 카드 표시 → 사유 입력 실행 / 취소 버튼. (ADR-0030 UI가 이 interrupt를 렌더)

- [ ] **Step 4: eval 회귀 점수**

Run: `.venv/bin/python -m tests.eval.runner`
Expected: 회귀 점수 확인. 하락 시 원인 명시(라우팅 변경이 doc_search 분류에 영향 주는지 점검).

- [ ] **Step 5: (검증 통과 시) 마무리**

수동 검증 결과를 보고. 실패 시 systematic-debugging으로 전환.

---

## Self-Review (작성자 점검 완료)

**Spec 커버리지:**
- 설계 A(라우팅: 라벨 리네임 + 프롬프트 확장) → Task 2(리네임) + Task 3(확장) ✓
- 설계 B(도구 단일인자) → Task 1 ✓
- ADR-0031/0032 기록 + 에이전트-우선 기각 명시 → Task 4 ✓
- 테스트(라우터·도구·헬퍼·프롬프트·잔존 grep) → Task 1,2,3,4 ✓
- 통합/수동(권한→JUSTIFY)·eval → Task 5 ✓

**Placeholder 스캔:** 모든 코드 스텝에 실제 코드·정확한 명령·기대 출력 수록. TODO/모호 지시 없음 ✓

**타입·이름 일관성:** `single_text_arg(args, *, prefer)` 시그니처가 Task 1 정의·sql_tool·permission_tool 호출에서 일치. route 라벨 `agent`가 router.py·state.py·builder.py·prompts.py·전 테스트에서 일관. `_VALID_ROUTES`에 `agent` 포함과 `route == "agent"` 일치 ✓

**커밋 green 보장:** Task 2가 코드+해당 테스트를 한 커밋에 묶어 중간 빌드 깨짐 없음(지난 작업 교훈 반영). Task 1·3도 각각 self-contained ✓
