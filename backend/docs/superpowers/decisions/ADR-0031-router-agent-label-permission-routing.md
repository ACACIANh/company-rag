# ADR-0031: 라우터 route 라벨 `agent` 명명 + 권한관리 라우팅 포함

> **Status**: 🟢 적용완료   <!-- 🟢 적용완료 · 🔵 승인됨 · ⚪ 제안됨 · 🟡 보류 · 🟣 대체됨 · ⚫ 폐기 -->

**Date**: 2026-06-03
**Context**: ROUTER_PROMPT이 비문서 경로(`tool_call`)를 "업무 DB 조회"로만 정의해, SP2b(ADR-0029)로 추가된 권한관리(`manage_permission`) 질문이 도구 경로에 안정적으로 도달하지 못했다(라우터가 doc_search로 폴백, rewrite_query가 더 불안정하게 만듦). web JUSTIFY 카드(ADR-0030)가 실서비스에서 뜨지 않는 원인이었다.

## Decision
- 2-way 라우팅 유지(`doc_search` vs `agent`). 분기 뒤 ReAct 에이전트(ADR-0023)가 SQL/권한 도구를 선택하는 구조 보존.
- route 라벨 `tool_call` → `agent`로 명명. 도구 중립적이며("위임하면 알아서 처리하는 에이전트") 목적지 노드 `agent`와 정렬.
- ROUTER_PROMPT의 `agent` 분기를 "업무 DB 조회·집계 또는 사내 권한 관리(부서 멤버십·폴더 접근·SQL 실행 권한 부여/회수)"로 확장. 판정 기준을 "문서 서술 vs 도구 처리"로 재구성, 권한 few-shot 추가, "모호하면 doc_search" 편향 유지.

## 고려했으나 기각한 대안 — 에이전트-우선 단일 진입
라우터를 없애고 단일 ReAct 에이전트가 문서검색(도구화)·SQL·권한을 모두 도구 선택으로 처리. 기각: (1) doc_search의 Self-RAG 그래프(rewrite→multi_query→permission pre-filter→retrieve→grade→hallucination→retry)를 한 도구로 싸야 해 그래프 레벨 제어 상실, (2) 흔한 문서질문까지 ReAct 루프로 비용·지연 증가, (3) 결정성·디버깅 저하, (4) ADR-0022/0023 전제 뒤집음.

## Consequences
- 권한 질문이 `agent`로 안정 라우팅(라이브 7/7 검증) → `manage_permission` → 게이트 → confirm(interrupt) → JUSTIFY 카드 동작.
- ADR-0022(데이터-원천 분류) 개정: 판정 축이 "테이블 값" → "문서 vs 도구"로 일반화.
- 도구 인자 결함은 ADR-0032에서 별도 해소(권한 JUSTIFY 동작에 함께 필요).

## 관련 ADR
- [[ADR-0022]] 라우터 분류 — 본 ADR이 개정
- [[ADR-0023]] tool_call ReAct 루프 — 보존, `agent` 라벨로 노드명 정렬
- [[ADR-0029]] manage_permission — 라우팅 도달 대상
- [[ADR-0030]] web JUSTIFY 카드 — 이 수정으로 실환경 동작
- [[ADR-0032]] 게이트 도구 단일인자 — 함께 필요
