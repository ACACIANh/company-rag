# ADR-0036: "출처를 찾지 못했습니다" 멘트 — RAG 경로 한정 표시

> **Status**: 🟢 적용완료

**Date**: 2026-06-04
**Context**: `generate.py`의 `_NO_DOC_NOTICE`("⚠️ 관련 사내 문서를 찾지 못했습니다.")는 `is_doc_search and no_relevant_docs` 조건에만 반환된다. 그러나 프론트엔드가 `citations`가 빈 배열이면 출처 없음 문구를 노출해, agent·capability 경로(citations 항상 `[]`)에서도 같은 멘트가 표시된다.

## Options
| 선택지 | 트레이드오프 |
|--------|------------|
| A. API 응답에 `route` 필드 추가 → 프론트엔드가 `doc_search`일 때만 출처 없음 UI 표시 | 백/프론트 계약 변경, 가장 명확한 의미론 구분 |
| B. 백엔드에서 `citations` 대신 `no_source: bool` 플래그 추가 | route 노출 없이 intent만 전달, 단 필드 하나 추가 |
| C. `generate.py`에서 `_NO_DOC_NOTICE`를 answer 텍스트로 반환하는 대신 별도 필드로 전달 | 프론트 렌더 방식 분리 가능, 계약 변경 범위가 A와 유사 |

## Decision
**선택: A — API 응답에 `route` 필드 추가**

## Rationale
근본 원인은 프론트엔드가 `citations == []`를 "RAG 실패"로 해석하는 것인데, agent 경로는 애초에 문서 출처가 없는 게 정상이다. `route`를 응답에 포함하면 프론트가 맥락(어떤 경로로 답했는지)을 알고 UI를 달리 렌더할 수 있다.

- `doc_search` + `citations == []` → "출처를 찾지 못했습니다" 표시
- `agent` / `capability` + `citations == []` → 출처 섹션 자체를 숨김

구현 포인트:
1. `app/api/chat.py` ChatResponse — `route: str` 필드 추가
2. 그래프 실행 후 `state["route"]`를 응답에 포함
3. 프론트엔드 — `route === "doc_search"` 조건에서만 출처 없음 UI 노출
