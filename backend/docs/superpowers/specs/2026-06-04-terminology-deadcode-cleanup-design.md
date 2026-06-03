# 용어 정합 + 유령 코드 제거 (최소안) — 설계

> **Status**: ⚪ 제안됨
> **작성일**: 2026-06-04
> **관련**: ADR-0023(tool_call 에이전트화), ADR-0031(라우터 agent 라벨·라벨=노드명 정렬)

## 배경

프로젝트 전반의 용어 사용을 조사한 결과, 코드는 이미 표준(`agent`)으로 전환됐으나
문서·죽은 코드·라우팅 라벨에 옛 용어와 비일관이 남아 있다. `tool_call → agent`
변경(ADR-0031)의 정신을 이어, 잘못 노출된 용어를 표준으로 정합한다.

## 명명 원칙 (확정)

**캡슐화** — 외부 경계에 노출되는 이름은 역할(role)로, 내부 구현 디테일은
how(메커니즘)를 허용한다. 객체지향에서 공개 인터페이스는 의미론적 역할을 드러내고
내부 구현은 자유로운 것과 같다.

이 원칙을 적용한 결과:

- **유지(정당한 캡슐화)**: `citations`(내부 state) ↔ `sources`(외부 API 응답) 매핑,
  노드명 `multi_query`/`tool_gate`/`rewrite_query` 등 how 형태(전부 그래프 내부),
  `allowed_folders`(내부 state).
- **불변(외부 스키마)**: `AuditRecord`의 `generated_sql/sql_risk/gate_decision` 필드,
  FGA `capability:sql` — 영속 스키마·권한 계약이므로 이번 범위에서 손대지 않는다
  (DB 마이그레이션 없음).

작업은 아래 **세 변경**으로 수렴한다.

## 변경 1 — 유령 SQL 서브루틴 제거 (내부 dead code)

ADR-0023에서 고정 SQL 흐름(`sql_generate → classify_risk → gate → sql_execute/reject`)이
도구 불가지 ReAct 루프(`agent → tool_gate → confirm/justify_execute`)로 대체됐으나,
구 흐름의 노드·함수·state 필드가 그래프에 미연결인 채로 잔존한다. `builder.py`의
`add_node`/`add_conditional_edges` 전수 확인으로 미연결을 검증했다.

### 삭제 (노드 5개 + 각 전용 테스트, 총 10개 파일)
- `app/graph/nodes/sql_generate.py`, `sql_execute.py`, `sql_reject.py`,
  `classify_risk.py`, `tool_executor.py`
- 대응 `tests/app/graph/nodes/test_sql_generate.py`, `test_sql_execute.py`,
  `test_sql_reject.py`, `test_classify_risk.py`, `test_tool_executor.py`

### 부분 수정
- `app/graph/edges.py`: `route_after_gate`, `route_after_confirm` 함수 제거
  (이들은 더 이상 존재하지 않는 노드 `sql_execute`/`sql_reject`를 반환하며 그래프 미연결)
- `tests/app/graph/test_edges.py`: 위 두 함수의 import·테스트 블록 정리
- `app/graph/state.py`: `AgentState`의 죽은 필드 `generated_sql / sql_risk /
  gate_decision` 제거 (현재 어떤 노드도 이 state 필드를 읽지 않음 — 감사 로그는
  `PendingToolCall`의 `planned_action/risk/decision`에서 값을 취함)
- `app/graph/builder.py`: 두 초기화 블록(`answer_question`, `stream_answer`)에서
  해당 필드 초기화 제거
- `tests/app/graph/test_state.py`, `test_builder.py`: 제거된 필드 단언 반영

### 절대 유지 (살아있는 동명 의존 — 혼동 주의)
- `core.sql.gate`의 **함수** `gate_decision`, `core.sql.risk` — `tool_gate_node`가 사용
- `AuditRecord`의 **필드** `generated_sql/sql_risk/gate_decision` 및
  `tool_gate.py`/`justify_execute.py`가 이를 채우는 키워드 인자 — 외부 감사 스키마
- `tests/core/sql/test_gate.py`, `tests/core/observability/audit/test_postgres_sink.py`

> 이름 충돌 경고: state 필드 `gate_decision`(죽음)과 함수 `gate_decision`(살아있음),
> AuditRecord 필드 `gate_decision`(외부)이 동명이다. 제거 대상은 **오직 AgentState의
> 필드**다.

## 변경 2 — 라우팅 라벨 정렬 버그

`route_after_agent`는 한 분기에서 노드명(`"tool_gate"`)을, 다른 분기에서 상태명
(`"agent_done"`)을 반환하는 함수 내부 비일관이다. 실제 목적지 노드는 `agent_answer`다.
ADR-0031 원칙②(라우팅 라벨 = 목적지 노드명 정렬)에 맞춰 정렬한다. 동작은 불변.

- `app/graph/edges.py`: `route_after_agent` 반환값 `"agent_done"` → `"agent_answer"`
- `app/graph/builder.py:121`: 매핑을
  `{"tool_gate": "tool_gate", "agent_answer": "agent_answer"}`로
- `tests/app/graph/test_edges.py`: `route_after_agent` 기대값 갱신

## 변경 3 — 외부 문서의 `tool_call` 잔재 교정

코드·신규 ADR은 모두 `agent`로 전환됐으나, 외부 독자가 보는 문서가 옛 용어에 멈춰 있다.

- `backend/CLAUDE.md` — "route 필드로 doc_search/**tool_call** 분기" 등
- `docs/architecture/backend-internals.md` — 다이어그램·상태 테이블·설명 약 6곳
- `docs/architecture/interview-questions-with-answers.md` — 약 3곳
- **제외**: `docs/superpowers/plans/*` 레거시 문서는 완료된 phase의 역사 기록이므로
  의도적으로 보존한다.

## 범위 밖 (명시적 비목표)

- 외부 스키마 재명명(AuditRecord 필드, FGA `capability:sql`) — 마이그레이션 비용으로
  이번 범위 제외 (별도 과제로 기록 가능)
- 노드명·내부 state 필드의 how→role 재명명 — 캡슐화 원칙상 유지
- core/ 레이어 변경 — 규칙 5 준수
- `LLMClient.complete()` 동기/비동기 등 설계 이슈 — 용어가 아니므로 제외

## 검증 (DoD)

1. 전체 단위 테스트 통과 (삭제분 반영 후 그린)
2. `tests/eval/runner.py` 회귀 점수 — 활성 그래프 흐름 불변이므로 동일 기대,
   하락 시 원인 명시
3. **ADR-0033** 신규 작성: "캡슐화 기반 명명 표준 + 유령 SQL 코드 제거".
   `python -m scripts.gen_adr_index`로 `decisions/README.md` 재생성
4. `backend/CLAUDE.md` 아키텍처 섹션·ADR 섹션 갱신

## 커밋 단위

세 변경을 한 PR로 묶는다(사용자 결정). 내부적으로 변경 1(dead code) → 변경 2(정렬) →
변경 3(문서)+ADR 순으로 커밋을 나눠 리뷰 가독성을 확보한다.
