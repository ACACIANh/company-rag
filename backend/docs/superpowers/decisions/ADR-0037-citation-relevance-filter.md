# ADR-0037: citations — 실제 사용 문서만 표시

> **Status**: ⚪ 제안됨

**Date**: 2026-06-04
**Context**: `generate_node`에서 `citations`를 `state["documents"]` 전체(rerank 후 top_k=5)로 만든다(`citations = [SourceRef(source=d.chunk.source) for d in state["documents"]]`). LLM이 실제로 참조하지 않은 문서도 출처로 표시되어 신뢰도를 해친다.

## Options
| 선택지 | 트레이드오프 |
|--------|------------|
| A. RAG_GENERATE 프롬프트에 "사용한 문서 번호를 답변 끝에 `[출처: 1,3]` 형태로 표기" 추가 → 번호 파싱 후 필터 | LLM 추론 비용 일부 증가, 정확도 높음. 파싱 실패 시 fallback 필요 |
| B. `relevance_score`를 개별 문서 단위로 계산해 임계값 미만 제거 | 현재 relevance_score는 문서 묶음 단위 — 개별 점수화 위해 grade 로직 변경 필요 |
| C. reranker 점수 기준 상위 N개만 유지 (예: top 3 → citations도 3개) | 간단, 그러나 LLM 실제 사용 여부와 무관 |
| D. citations dedup만 적용 (동일 source 중복 제거) | 최소 변경, 근본 문제 미해결 |

## Decision
**선택: A — 프롬프트에 출처 번호 표기 지시 추가 + 파싱 필터**

## Rationale
LLM이 어떤 청크를 실제로 사용했는지는 LLM 자신만 안다. 프롬프트로 근거 번호를 명시하도록 유도하면 A) 답변 품질도 올라가고 B) 파싱 결과로 citations를 필터할 수 있다. D(dedup)는 B를 함께 적용하면 된다.

파싱 실패 fallback: 번호를 추출 못 하면 전체 documents를 citations로 유지 (현재 동작 보존).

구현 포인트:
1. `RAG_GENERATE` 프롬프트 끝에 지시 추가:
   ```
   답변 마지막 줄에 실제 참조한 문서 번호를 [출처: 1,3] 형식으로 표기하세요. 참조 없으면 생략.
   ```
   문서는 `[1] ...`, `[2] ...` 형식으로 번호 부여하여 context에 주입
2. `generate_node` — 응답에서 `[출처: ...]` 파싱 → 해당 인덱스의 document만 citations 포함
3. dedup: 동일 `source` 중복 제거 (D와 함께 적용)
