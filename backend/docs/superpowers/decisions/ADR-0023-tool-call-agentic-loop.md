# ADR-0023: tool_call 경로를 게이트된 도구-디스패치 ReAct 루프로 전환

> **Status**: 🟢 적용완료   <!-- 🟢 적용완료 · 🔵 승인됨 · ⚪ 제안됨 · 🟡 보류 · 🟣 대체됨 · ⚫ 폐기 -->

**Date**: 2026-06-03
**Context**: `tool_call` 경로가 SQL 하나에 하드코딩된 고정 서브루틴(`sql_generate→classify_risk→gate→sql_execute/confirm/sql_reject`)이라, 향후 "권한 부여/회수" 같은 도구를 추가하기 어렵다. 도구 불가지 ReAct 루프로 전환하고, 신원×위험도 게이트(ADR-0016)를 모든 도구에 공통으로 적용되는 "도구-실행-전 인터셉터"로 일반화한다. 설계: `docs/superpowers/specs/2026-06-03-tool-call-agentification-design.md`.

## Options

### 토폴로지
| 선택지 | 트레이드오프 |
|--------|------------|
| **A. 단일 ReAct 에이전트 + 게이트된 도구들** | router가 tool-using 에이전트에 위임, 에이전트가 도구 선택. 게이트는 도구-실행-전 인터셉터. 기존 게이트·HITL·감사 전부 재사용. "도구 추가 = 레지스트리 등록". |
| B. 멀티에이전트 supervisor + handoff | 독립 에이전트로 라우팅. 표현엔 충실하나 라우팅·상태 공유 복잡도가 과함(도구 2개뿐인 현 시점 YAGNI). |

### 도구 표현
| 선택지 | 트레이드오프 |
|--------|------------|
| 프롬프트 기반 디스패치 | 구조화 텍스트 파싱. core LLMClient 불변. 단발 도구. |
| **LangChain Tool + bind_tools chat 모델** | `create_chat_llm().bind_tools()`. 정석·tool_call_id. `langchain-anthropic`(이미 pyproject 선언, openai는 설치됨) 사용. |

### SQL 도구 입력 단위
| 선택지 | 트레이드오프 |
|--------|------------|
| **NL 질문 입력** (`query_business_data(question)`) | 도구 내부가 NL→SQL(값 힌트)·위험도·실행. ADR-0021/0017 재사용. |
| SQL 직접 입력 (`run_sql(query)`) | 토폴로지 단순하나 값 힌트 지점 애매, LLM이 임의 SQL 작성. |

## Decision

**선택: 토폴로지 A + LangChain Tool/bind_tools + SQL 도구는 NL 질문 입력.**

- **도구 레지스트리**(`app/graph/tools/`): 도구 = LangChain `Tool` 정의 + 핸들러(`plan(args)->(계획된_동작, 위험도)`, `aexecute(계획)->결과`). SQL이 첫 등록 도구 `query_business_data`.
- **agent 노드**(`app/graph/nodes/agent.py`): `create_chat_llm(cfg).bind_tools(tool_defs)`를 `agent_messages`로 호출. 첫 진입 시 시스템 지시+질문 시드.
- **tool_gate 인터셉터**(`app/graph/nodes/tool_gate.py`): 각 도구 호출을 `plan`으로 구체화 → `gate_lookup(신원, 위험도)` → ALLOW=즉시 실행, DENY=거부 ToolMessage, JUSTIFY=`pending_tool_calls` 적재. 모든 결정 감사 기록(ADR-0018).
- **confirm + justify_execute**: JUSTIFY는 confirm이 계획된 SQL을 interrupt 페이로드에 노출하고 사유를 받음(ADR-0027), justify_execute가 실행/거부 후 pending 비움.
- **AgentState 확장**: `agent_messages: Annotated[list[AnyMessage], add_messages]`, `pending_tool_calls: list[PendingToolCall]`. `MessagesState` 금지 준수.
- **프리빌트 `create_react_agent` 미사용**: 도구를 자동 실행해 게이트가 끼어들 틈이 없으므로 커스텀 그래프(`agent↔tool_gate↔confirm/justify_execute` 루프)로 구성. `recursion_limit`로 루프 상한(doc_search 재시도 보존 위해 25 유지).

### 토폴로지
```
router[tool_call] → agent ─(tool_calls)→ tool_gate ─ ALLOW→실행, DENY→거부 (ToolMessage) → agent
                      ↑                              └ JUSTIFY → confirm(계획 노출·사유) → justify_execute → agent
                      └─(no tool_calls)→ agent_answer → save_memory
```

## Rationale

- 권한 부여/회수는 SQL 실행과 동형인 "게이트가 통제하는 고위험 side-effect"라, 이미 만든 게이트·HITL·감사 인프라에 그대로 얹힌다 — A가 사용자 동기("권한 도구 추가 용이")를 최소 비용으로 달성. B(멀티에이전트)는 도구 2개뿐인 지금 과설계.
- 도구 위험도는 *구체화된 동작*(생성된 SQL)에 달려 있으므로, 게이트는 `plan`(동작 구체화) 직후·`aexecute` 직전에 돈다. 이 `plan→게이트→execute` 패턴이 향후 권한 도구(plan=grant/revoke 튜플, 위험도=권한쓰기=고위험)에 일반화된다.
- `core` 추상화(`LLMClient`)는 문자열 전용이므로 건드리지 않고, LangChain tool-calling은 `app/graph/`에만 둔다(레이어 규칙 준수). 기존 문자열 노드(router 등)와 chat 모델 에이전트가 공존한다.
- SQL NL 입력은 ADR-0021 값 힌트·ADR-0017 위험도 분류를 그대로 재사용해 생성 품질·PII 경계를 유지한다.

## 미해결 / 후속

- **HITL API resume 종단**은 ADR-0024에서 완결(본 ADR은 그래프 내부 루프·게이트까지).
- **sync invoke — 🟢 해소(2026-06-04, feat/adr-followups)**: `agent_node`를 `async def` + `await chat_model.ainvoke(...)`로 전환(피어 LLM 노드 `generate`/`retrieve`와 일관). 이벤트 루프 블로킹 우려 제거. builder 배선(`partial`)·그래프(`graph.ainvoke`)는 무변경. 전체 테스트 스위트 통과.
- **SP2(권한 관리 도구)**: `fga_grant_revoke`를 고위험 도구로 등록 — 별도 스펙.
- 기존 노드 함수(`sql_generate`/`classify_risk`/`gate`/`sql_execute`/`sql_reject`)는 그래프에서 분리됐으나 로직 재사용·학습 목적으로 보존(CLAUDE.md 규칙 5).

## 영향받는 결정

- [ADR-0016](ADR-0016-identity-risk-sql-gate.md) — 게이트를 SQL 전용 고정 노드 → 도구 불가지 인터셉터로 재배치.
- [ADR-0017](ADR-0017-sql-risk-classification.md) · [ADR-0021](ADR-0021-sql-schema-value-hints.md) — SQL 도구 핸들러 내부에서 재사용.
- [ADR-0027](ADR-0027-justify-and-approve-self-service-gate.md) — JUSTIFY_AND_APPROVE 흐름을 루프 내 confirm/justify_execute로 재배치.
- 메모리의 옛 ADR-0023~0026 4분할 스케치는 본 ADR-0023(루프)·[ADR-0024](ADR-0024-hitl-api-resume.md)(HITL 종단) 2분할로 대체. 0025·0026은 결번.
