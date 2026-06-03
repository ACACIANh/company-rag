# ADR-0033: 캡슐화 기반 명명 표준 + 유령 SQL 코드 제거

> **Status**: 🟢 적용완료   <!-- 🟢 적용완료 · 🔵 승인됨 · ⚪ 제안됨 · 🟡 보류 · 🟣 대체됨 · ⚫ 폐기 -->

**Date**: 2026-06-04

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
3. 외부 문서(`CLAUDE.md`, `backend-internals.md`/`.html`, `interview-questions`)의
   `tool_call` 교정.

**범위 밖**: 외부 스키마 재명명(`AuditRecord` 필드, FGA `capability:sql`)은 마이그레이션
비용으로 보류. `core/`는 규칙 5에 따라 불변. 레거시 plan 문서는 역사 기록으로 보존.

## Consequences

- 그래프 토폴로지·노드 동작 불변 → 기능 회귀 없음. DB 마이그레이션 없음.
- dead code 제거로 용어 혼란 표면적이 감소하고, 라벨=노드명 일관성이 확보된다.
- 후속 과제: 외부 감사 스키마(`generated_sql/sql_risk`)의 도구 불가지 재명명(별도 ADR).

## 관련 ADR

- [[ADR-0023]] tool_call 에이전트화 — ReAct 루프 도입, SQL 노드 제거 전거
- [[ADR-0031]] 라우터 agent 라벨 — 명명 정착, 라벨=노드명 원칙 확립
- Spec: `docs/superpowers/specs/2026-06-04-terminology-deadcode-cleanup-design.md`
