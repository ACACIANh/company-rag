# 라우터 route 명명 + 게이트 도구 단일인자 처리 설계

**Date**: 2026-06-03
**Status**: 설계 승인됨 (구현 전)

## 배경 / 문제

web HITL JUSTIFY interrupt UI(ADR-0030)를 실환경에서 검증하려다 두 개의 선재 백엔드 결함을 발견했다. 둘 다 권한부여 질문 → `manage_permission` → 게이트 → `confirm(interrupt)` → **JUSTIFY 카드** 경로를 막는다.

1. **라우터가 권한 질문을 인지하지 못함.** `ROUTER_PROMPT`이 비(非)문서 경로(`tool_call`)를 "업무 DB(employees·sales) 조회"로만 정의한다. 권한관리에 대한 설명이 없어, "alice를 finance에 추가해줘" 같은 권한 질문이 `doc_search`로 새거나(표현·rewrite에 따라 들쭉날쭉) 도구 경로에 안정적으로 도달하지 못한다.

2. **게이트 도구가 모델 인자를 잘못 읽음.** SQL·권한 도구는 `langchain_core.tools.Tool(func=lambda question: "")` / `func=lambda instruction: ""`로 정의된 **단일 문자열 입력 레거시 Tool**이다. 모델이 bind_tools 호출 시 인자를 `{'__arg1': '...'}`로 넘기는데, 두 핸들러의 `plan()`이 각각 `args["question"]` / `args["instruction"]`로 읽어 **`KeyError`**로 크래시한다(`{"type":"error","message":"'question'"}`).

→ 두 결함이 함께 해결되어야 권한 JUSTIFY가 실제로 동작한다. 라우팅만 고치면 권한 질문이 도구 경로로 가도 도구가 `__arg1`로 크래시한다.

검증 근거(2026-06-03 라이브):
- 격리 `router_node` 호출: "권한 부여" → `doc_search`, "멤버로 추가" → `agent`(표현 의존). 라이브 `/chat/stream`에선 `rewrite_query`가 끼어 더 불안정.
- bind_tools 모델 invoke: `query_business_data` 호출 args = `{'__arg1': '전 직원 급여 조회'}`.

## 결정

### A. 라우팅 (ADR-0031로 기록)

- **2-way 구조 유지**: `doc_search`(사내 문서 검색 Self-RAG 파이프라인) vs **`agent`**(도구로 처리). SQL·권한 분기는 종전대로 `agent` 노드(ReAct, ADR-0023)가 도구 선택으로 수행. 분기 뒤 흐름 무변경.
- **route 라벨 `tool_call` → `agent`로 명명.** 도구 중립적이고("위임하면 알아서 처리하는 에이전트"), 목적지 노드 `agent`와 정렬된다. route 값과 노드명이 동일해지나 충돌 아님(조건부 엣지가 `"agent" → "agent" 노드`로 매핑).
- **ROUTER_PROMPT 확장**: `agent` 분기 설명을 "업무 DB 조회/집계 **또는** 사내 권한 관리(부서 멤버십·폴더 접근·SQL 실행 권한 부여/회수)를 도구로 처리하는 질문"으로 넓힌다. 판정 기준을 "문서 서술로 답하는가 vs 도구로 처리하는가"로 재구성하고, 권한 few-shot 1개 추가. "모호하면 doc_search" 보수 편향은 유지.

**고려했으나 기각한 대안 — 에이전트-우선 단일 진입**: 라우터를 없애고 단일 ReAct 에이전트가 처음부터 문서검색(도구화)·SQL·권한을 모두 도구 선택으로 처리. 기각 사유: (1) doc_search의 Self-RAG 그래프(rewrite→multi_query→permission pre-filter→retrieve→grade→generate→hallucination→retry)를 통째로 한 도구로 싸야 해 그래프 레벨 제어를 잃음, (2) 흔한 문서질문까지 ReAct 루프를 거쳐 비용·지연 증가, (3) 결정성·디버깅 저하, (4) ADR-0022/0023 전제 뒤집음. 별도 ADR로 남기지 않고 본 결정의 기각 대안으로만 기록.

### B. 게이트 도구 단일 인자 처리 (ADR-0032로 기록)

- SQL·권한 두 핸들러의 `plan(args)`가 단일 NL 입력을 **견고하게 추출**한다. named 키(`question`/`instruction`)가 있으면 그것을, 없으면 단일 입력 폴백(`__arg1`, 또는 args의 단일 값)을 쓴다.
- 공용 헬퍼 하나로 중복 제거: `app/graph/tools/_args.py`의 `single_text_arg(args: dict, *, prefer: str) -> str` — `args.get(prefer)` → `args.get("__arg1")` → args의 단일 값 → `""` 순으로 폴백. 두 핸들러가 이 헬퍼로 추출.
- 도구 contract(단일 NL 입력)·게이트·플랜·실행 로직은 그대로. 추출 지점만 방어적으로 교정.

## 컴포넌트 / 변경 지점

### A. 라우팅
| 파일 | 변경 |
|------|------|
| `app/graph/nodes/router.py` | `_VALID_ROUTES = {"doc_search", "agent"}`; `route == "agent"`로 `tool_input` 판정 |
| `app/graph/state.py:22` | `route: Literal["doc_search", "agent"]` |
| `app/graph/builder.py:103` | 조건부 엣지 매핑 키 `"agent": "agent"` + 117행 주석 갱신 |
| `app/graph/prompts.py` | ROUTER_PROMPT `agent` 분기 설명 확장 + 권한 few-shot + 출력 예시 `agent:none` |
| `app/graph/edges.py` `route_after_router` | 로직 무변경(`state["route"]` 반환). multi_query 특례는 doc_search 전용이라 영향 없음 |

`tool_calls`·`pending_tool_calls`·`tool_call_id`(LLM 도구호출 객체)는 **불변** — 이름이 비슷할 뿐 route 라벨과 무관.

### B. 도구 인자
| 파일 | 변경 |
|------|------|
| `app/graph/tools/_args.py` (신규) | `single_text_arg(args, *, prefer)` 헬퍼 |
| `app/graph/tools/sql_tool.py:47` | `question = single_text_arg(args, prefer="question")` |
| `app/graph/tools/permission_tool.py:37` | `instruction = single_text_arg(args, prefer="instruction")` |

## 데이터 흐름 (수정 후)

권한 질문: `rewrite_query → router(=agent) → agent(ReAct, manage_permission 선택, args={'__arg1':...}) → tool_gate(plan: 헬퍼로 instruction 추출 → RISK_GRANT → c_level justify_grant → JUSTIFY) → confirm(interrupt 방출) → [web JUSTIFY 카드]`.
SQL 대량조회: `... router(=agent) → agent(query_business_data) → tool_gate(헬퍼로 question 추출 → RISK_BULK_SELECT → justify_bulk_select → JUSTIFY) → confirm(interrupt)`.

## 테스트

### A. 라우팅
- `router_node` 단위: mock LLM이 `"agent:none"` 반환 → `route=="agent"`, `tool_input` 채워짐; `_VALID_ROUTES`에 `"agent"` 포함.
- `ROUTER_PROMPT` 단위: 권한 관련 문구(예: "권한")가 프롬프트에 포함됨을 assert.
- 잔존 점검: route-값 `"tool_call"` 문자열이 `app/`에 0건(`tool_calls`/`pending_tool_calls`/`tool_call_id` 제외).
- 기존 `tests/app/graph/test_state.py:47` `"route": "agent"`로 갱신.

### B. 도구 인자
- `sql_tool.plan` 단위: `args={'__arg1': "전 직원 급여"}` 입력 시 KeyError 없이 NL 추출(SQL 생성은 mock LLM). 회귀: `args={'question': "..."}`도 동일 동작.
- `permission_tool.plan` 단위: `args={'__arg1': "alice를 engineering에 추가"}` 입력 시 KeyError 없이 instruction 추출(파싱은 mock LLM).
- 헬퍼 단위: named 우선, `__arg1` 폴백, 단일 값 폴백, 빈 args 경계.

### 통합/수동 (DoD)
- 라이브: admin 로그인 → "alice를 engineering 부서에 추가해줘" → route=agent → JUSTIFY interrupt 카드 → 사유 입력 실행 / 취소.
- eval 회귀 점수 확인(하락 시 원인 명시).

## 범위 밖
- 에이전트-우선 단일 진입(위 기각).
- web interrupt UI는 ADR-0030으로 이미 완료(이 작업은 백엔드만; UI는 무변경으로 동작).

## 관련 ADR
- ADR-0022 라우터 데이터-원천 분류 — 본 변경이 개정(라벨·범위 확장).
- ADR-0023 tool_call ReAct 루프 — 보존(분기 뒤 무변경). `agent` 라벨로 노드명과 정렬.
- ADR-0029 manage_permission — 이 도구의 `__arg1` 결함이 B에서 해소.
- ADR-0030 web JUSTIFY 카드 — 이 백엔드 수정으로 실환경 동작 가능.
