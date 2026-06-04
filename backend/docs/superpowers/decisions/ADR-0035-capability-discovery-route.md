# ADR-0035: 기능 안내 route 추가 — capability discovery

> **Status**: 🟢 적용완료

**Date**: 2026-06-04
**Context**: "뭘 할 수 있어?", "어떤 기능 있어?" 같은 질문에 현재 라우터가 `doc_search`로 기울어 문서 검색을 시도하거나 불명확한 답을 낸다. 시스템이 제공하는 기능(사내문서 검색·DB 조회·권한 관리)을 명확히 안내하는 경로가 필요하다.

## Options
| 선택지 | 트레이드오프 |
|--------|------------|
| A. 라우터에 `capability` route 추가 + 정적 안내 노드 | 라우터 분기 1개 증가, 안내 내용을 코드에서 관리 — 기능 추가 시 텍스트 동기화 필요. LLM 미사용으로 비용 없음 |
| B. 라우터 프롬프트 few-shot에 capability 예시 추가 → `doc_search`로 흡수 | 별도 노드 불필요, 그러나 문서 검색 실패 시 `_NO_DOC_NOTICE` 반환 — 기능 안내가 "찾지 못했습니다"로 끝남 |
| C. `agent` 경로의 `_SYSTEM` 프롬프트에 기능 목록 삽입 | agent 노드 재사용, LLM이 동적으로 안내 — 그러나 도구 목록과 혼동 가능, 비용 발생 |

## Decision
**선택: A — `capability` route 추가 + 정적 안내 노드**

## Rationale
기능 안내는 문서나 DB에 의존하지 않고 시스템 자체를 설명하는 메타 질문이다. 라우터에 `capability` route를 추가하고, 정적 텍스트를 반환하는 `capability_node`를 두면 LLM 비용 없이 일관된 안내를 제공한다.

안내 내용(초안):
- **사내 문서 검색** (`doc_search`): 정책·규정·절차·가이드 등 문서 기반 질문
- **업무 DB 조회** (`agent`): 직원·매출 등 테이블 값 조회·집계
- **권한 관리** (`agent`): 부서 멤버십·폴더 접근·SQL 실행 권한 부여/회수
- (확장 예정) 외부 연동·알림 등

구현 포인트:
1. `router.py` — `_VALID_ROUTES`에 `"capability"` 추가, ROUTER_PROMPT에 few-shot 예시 추가
2. `capability_node` 신규 추가 — 정적 안내 텍스트 반환, `save_memory`로 연결
3. `builder.py` — `route_after_router` 분기에 `"capability": "capability"` 추가
4. `AgentState` — `route` Literal에 `"capability"` 추가
