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

## 추가 조치 (구현·검증 중 발견)
프롬프트 확장만으로는 부족했다. `rewrite_query`(문서검색 편향)가 라우터·에이전트보다 먼저 돌며 액션·명령 질문("…추가해줘")을 "…절차/방법은?"으로 재작성해, 라우팅이 doc_search로 새고(라이브 1/6) 에이전트가 도구를 흐리게 호출했다. 라이브 검증으로 확인 후 세 가지를 추가했다:
- **라우팅 판정을 원본 `question` 기준으로** (`router.py`) — rewrite의 LLM 비결정성과 무관하게 결정적(격리 6/6 agent).
- **ReAct 에이전트 시드를 원본 `question`으로** (`agent.py`) — 에이전트가 사용자의 실제 요청으로 도구를 선택.
- **`rewrite_query` 의도 보존형으로** — 결과적으로 rewrite는 doc_search 검색(multi_query/retrieve) 입력 전용이 됨.

검증 결과: 명확히 표현된 권한 요청(`finance 폴더 접근 권한을 회수해줘`, `user-alice를 engineering 부서 멤버로 추가해줘`)과 SQL 대량 조회는 JUSTIFY interrupt가 안정적(4/4), 문서 질문은 doc_search 정상.

## 범위 밖 (후속 과제)
비격식 권한 표현("alice를 engineering 부서에 추가해줘")은 약 50%만 JUSTIFY로 이어진다. 원인은 라우팅·도구 인자가 아니라 **권한 NL 파싱(ADR-0029, `PERMISSION_PARSE_PROMPT`)이 `alice→user:user-alice`/`추가→member` 매핑을 들쭉날쭉**하게 해 절반이 검증 실패(RISK_DENY)로 빠지기 때문이다. 이는 본 ADR(라우팅·라벨)과 독립된 선재 견고성 이슈로, ADR-0029 후속으로 남긴다.

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
