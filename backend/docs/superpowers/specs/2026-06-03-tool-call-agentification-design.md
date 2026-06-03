# tool_call 에이전트화 (SP1) — 게이트된 도구-디스패치 ReAct 루프

**Date**: 2026-06-03
**Status**: 설계 (구현 전)
**관련 ADR(예정)**: ADR-0023(루프 토폴로지·도구 레지스트리·게이트 인터셉터), ADR-0024(HITL 종단 완결)
**관련 기존 ADR**: ADR-0016(신원×위험도 게이트), ADR-0017(SQL 위험도 분류), ADR-0018(감사 로그), ADR-0021(SQL 값 힌트), ADR-0027(JUSTIFY_AND_APPROVE)

## 1. 동기와 범위

### 동기
현재 `tool_call` 경로는 고정 서브루틴(`sql_generate → classify_risk → gate → sql_execute/confirm/sql_reject → generate`)으로, **단발성**(SQL 1회 생성·실행)이며 도구가 SQL 하나에 하드코딩돼 있다. 사용자의 목표는 **향후 "권한 부여/회수" 같은 도구를 쉽게 추가**할 수 있는 구조다. 이를 위해 tool_call 경로를 **도구 불가지(tool-agnostic) ReAct 루프**로 전환하고, 게이트를 모든 도구에 공통으로 적용되는 "도구-실행-전 인터셉터"로 일반화한다.

부차적으로, 현재 **JUSTIFY_AND_APPROVE의 `interrupt()`를 실제 API로 재개하는 경로가 없다**(`app/api`에 resume 처리 0건). HITL 게이트가 테스트에서만 동작하고 실서비스 종단에서는 미완성이다. SP1에서 이 종단을 메운다.

### 토폴로지 결정 (대안 비교)
- **A. 단일 ReAct 에이전트 + 게이트된 도구들 (채택)**: router가 tool-using 에이전트에 위임, 에이전트 내부에서 LLM이 도구 선택. 게이트가 도구-실행-전 인터셉터. 기존 게이트·HITL·감사 인프라를 그대로 재사용하며, "도구 추가 = 레지스트리 등록"이 된다.
- B. 멀티에이전트 supervisor + handoff (기각): 독립 에이전트로 라우팅. 표현엔 충실하나 라우팅·상태 공유 복잡도가 과함. 도구가 많아지면 A 위에 얹을 수 있는 후속.

권한 부여/회수는 본질적으로 "게이트가 통제하는 고위험 side-effect"라 SQL 실행과 동형이고, 이미 만든 게이트 인프라에 그대로 얹히므로 A가 최소 비용으로 동기를 달성한다.

### 범위
- **SP1 (본 스펙)**: SQL을 첫 등록 도구로 하는 게이트된 도구-디스패치 에이전트 + HITL 종단 완결. SQL은 동작 동등하되 이제 에이전틱·재개 가능 구조.
- **SP2 (범위 밖, 별도 스펙)**: 실제 `fga_grant_revoke` 권한 관리 도구. SP1 위에 "등록만" 하면 되도록 설계.

## 2. 도구 표현 방식 결정

`LLMClient`(core)는 문자열 in/out 전용(`complete`/`stream`)으로 네이티브 tool-calling이 없다. 도구 호출 표현으로 **LangChain `Tool` + `bind_tools` chat 모델**을 채택한다(`core/llm/factory.py`의 기존 `create_chat_llm()` 정식 사용).

결과:
1. **새 의존성 `langchain-anthropic`**(+필요 시 `langchain-openai`) 설치. 메모리의 "미사용 deps 제거" 판단을 되돌린다. DoD상 ADR 대상.
2. **프리빌트 `langgraph.prebuilt.create_react_agent`는 쓰지 않는다** — 도구를 자동 실행해 게이트가 끼어들 틈이 없다. **커스텀 그래프**로 agent↔gate↔execute 루프를 직접 구성한다.
3. **`AgentState` 확장** — 에이전트 내부 도구 대화를 담을 타입 필드. `MessagesState` 금지 규칙(CLAUDE.md)은 준수하고 `AgentState(TypedDict)` 확장만 한다.
4. **`tool_call_id` 매칭** — 네이티브 tool-calling은 한 턴에 도구 여러 개를 반환할 수 있으므로 게이트·HITL을 per-tool_call_id로 처리한다.

기존 문자열 기반 노드(router, sql_generate 등)는 core `LLMClient`를 계속 쓰고, **에이전트 노드만** chat 모델을 쓴다. 두 LLM 경로가 공존한다.

## 3. SQL 도구의 입력 단위 결정

**NL 질문 입력 (채택)**: 도구 = `query_business_data(question: str)`. 에이전트는 자연어 하위질문을 넘기고, 도구 핸들러 내부가 NL→SQL(현 `SQL_GENERATE_PROMPT` + ADR-0021 값 힌트) → 위험도 분류(ADR-0017) → 게이트 → 실행을 수행한다.
- 기각안(SQL 직접 입력 `run_sql(query)`): 토폴로지는 단순하나 값 힌트 주입 지점이 애매해지고, 게이트 이전에 LLM이 임의 SQL을 쓰게 된다.
- 채택 근거: ADR-0021/0017 투자를 그대로 재사용하고 SQL 생성 품질·PII 경계를 유지한다.

## 4. 컴포넌트와 데이터 흐름

### 핵심 통찰
도구의 위험도는 *구체화된 계획된 동작*(SQL의 경우 생성된 SQL)에 달려 있다. 따라서 각 도구는 다음 핸들러를 가진다:
- `plan(args) -> (계획된_동작, 위험도)` — SQL: NL→SQL 생성 + 위험도 분류.
- `execute(계획된_동작) -> 결과` — SQL: read-only 풀 실행.

게이트는 `plan` 직후·`execute` 직전에 `gate_lookup(신원, 위험도)`로 판정한다. 이 구조가 향후 권한 도구에 일반화된다(plan=grant/revoke 튜플, 위험도=권한쓰기=고위험).

### 토폴로지
```
router[tool_call] → agent ─(tool_calls 있음)→ gate(per tool_call)
                      ↑                          ├ ALLOW   → execute → ToolMessage
                      │                          ├ JUSTIFY → confirm(interrupt, 계획 노출) → execute/reject
                      └──────(ToolMessage 추가)──┤ DENY    → reject ToolMessage(실행 안 함)
                      │
                      └─(tool_calls 없음)→ 최종답변 → generate/save_memory
```

### 컴포넌트
1. **도구 레지스트리** (`app/graph/tools/`): 도구명 → (LangChain `Tool` 정의, 핸들러). 핸들러는 `plan`/`execute` + 위험도 분류기를 묶는다. SQL: `query_business_data`.
2. **agent 노드** (`app/graph/nodes/agent.py`): `create_chat_llm(cfg).bind_tools([...])`를 `agent_messages`로 호출 → AIMessage 반환. `tool_calls` 유무로 분기.
3. **tool_gate 노드** (`app/graph/nodes/tool_gate.py`): 각 tool_call에 대해 핸들러.plan → `gate_lookup` → 결정. ALLOW=즉시 execute, JUSTIFY=confirm 경유, DENY=거부 ToolMessage. 결정·실행을 감사 로그(ADR-0018)에 기록.
4. **confirm 노드**(기존 재사용·확장): JUSTIFY 경로 interrupt. 페이로드에 계획된 동작(SQL)·도구명·인자 포함. resume = 사유 문자열(ADR-0027). 빈 사유 = 거부.
5. **AgentState 확장**:
   - `agent_messages: Annotated[list[AnyMessage], add_messages]` — 에이전트 도구 대화.
   - `pending_tool_calls: list[PendingToolCall]` — interrupt를 넘어 보존할 in-flight 도구호출. `PendingToolCall`은 타입 구조(TypedDict 또는 dataclass)로 정의: tool_call_id·name·args·계획된_동작·위험도·결정. (CLAUDE.md "임의 dict 금지" 준수 — 익명 dict 금지)
6. **루프 상한**: langgraph `recursion_limit`로 폭주 차단.

## 5. HITL 종단 완결 (API resume)

- **interrupt 페이로드**: 계획된 SQL·도구명·인자·위험도를 담아 클라이언트가 "무엇을 승인하는지" 보게 한다.
- **API resume 루프** (`app/api/chat.py`): 그래프 호출 전 `aget_state(config)`로 스레드가 interrupt 상태인지 확인. interrupt 상태면 들어온 사용자 메시지를 **사유**로 해석해 `Command(resume=사유)`로 재개. 아니면 신규 질문으로 처리.
- **tool_call_id 매칭**: 여러 tool_call이 동시에 JUSTIFY면 어떤 호출의 사유인지 id로 매칭. (SP1 초기엔 단일 JUSTIFY를 기본 가정하되 구조는 멀티 대응.)
- 스트리밍 경로(`stream_answer`)도 동일 resume 분기 적용.

## 6. 에러 처리

- 도구 실행 오류 → `ToolMessage`에 오류 텍스트로 변환(루프 비차단, 현 `sql_execute` 패턴 계승).
- 위험도 분류 폴백·파싱 실패 → DENY(보수적, ADR-0017).
- 빈 사유/취소 → reject(ADR-0027).
- `recursion_limit` 도달 → 현재까지 결과로 최종답변 강제.

## 7. 테스트 전략

- **단위**: 도구 레지스트리·plan/execute, tool_gate 인터셉터(ALLOW/JUSTIFY/DENY × 신원), agent 노드 tool_calls 파싱.
- **통합**: 루프(단발 도구→답변), DENY 비차단, JUSTIFY interrupt→resume 실행, 멀티턴.
- **API**: interrupt 상태 스레드에서 다음 메시지 resume 종단.
- **회귀**: `tests/eval/runner.py` 점수(doc_search 무영향 확인).

## 8. ADR 분해

- **ADR-0023**: tool_call 에이전트 루프 토폴로지 + LangChain Tool/`bind_tools` 도입(+`langchain-anthropic` 의존성) + 게이트를 도구-실행-전 인터셉터로 재배치 + `AgentState` messages 확장. 도구 레지스트리·agent·tool_gate 노드·그래프 재배선.
- **ADR-0024**: HITL 종단 완결 — interrupt 페이로드에 계획된 동작 노출 + `app/api/chat.py` resume 루프 + tool_call_id 매칭.

(메모리의 옛 0023~0026 4분할 스케치는 본 2분할로 대체. 0025/0026 번호는 미사용 — 결번 처리.)

## 9. 레이어 경계 준수 (CLAUDE.md)

- `core/`는 LangGraph/LangChain 불가지 유지. LangChain `Tool`·`bind_tools`·`AnyMessage`는 전부 `app/graph/`에 둔다. `create_chat_llm()`은 core에 있으나 LangChain BaseChatModel을 **반환**할 뿐 core가 그래프를 알지는 않는다(기존 설계 유지).
- 게이트 정책(`core/sql/gate.py`)·위험도(`core/sql/risk.py`)·감사(`core/observability/audit/`)는 순수 로직으로 그대로 재사용.
- 노드는 순수 함수 지향. side effect는 core 호출(FGA·감사·SQL 풀)로만.

## 10. 미해결 / 후속

- **SP2**: `fga_grant_revoke` 권한 관리 도구(고위험) 등록 — 별도 스펙.
- **멀티 병렬 tool_call의 완전한 HITL**(여러 JUSTIFY 동시 대기) — SP1은 단일 JUSTIFY 기본 가정, 구조만 멀티 대응. 실제 병렬 JUSTIFY UX는 필요 시 후속.
- **`langchain-openai` 정리**: anthropic만 설치할지, 양 provider 모두 둘지 ADR-0023에서 확정.
- **eval 라우팅 지표**(ADR-0022 보류분)와 무관하게 진행.
