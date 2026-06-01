# ADR-0007: Reranker 임팩트 측정 지표 설계

> **Status**: 🟢 적용완료

**Date**: 2026-05-23
**Context**: Reranker 도입 전후 검색 품질 개선을 정량적으로 비교할 측정 체계 필요

## Options

| 선택지 | 트레이드오프 |
|--------|------------|
| recall@5만 유지 | 기존 지표 그대로. 단, reranker는 순서를 바꾸는 것이므로 pool이 같으면 recall@5 변화 없음 — 임팩트 감지 불가 |
| MRR + recall@[1,3,5] 추가 | 순위 민감 지표. recall@5보다 recall@1·@3이 reranker 효과에 훨씬 민감. 구현 비용 낮음 |

## Decision

**선택: MRR + recall@[1, 3, 5] 추가**

## Rationale

- Reranker는 문서를 새로 가져오는 게 아니라 순서를 바꾸는 것이므로, pool 크기가 같으면 recall@5는 변화 없음
- 임팩트를 보려면 retrieve(N=20) → reranker → top-k(5) 패턴이어야 하고, 이때 recall@1·@3·MRR이 순위 변화를 포착
- MRR(Mean Reciprocal Rank): 정답 문서가 몇 위인지 역수 평균 — reranker 효과에 가장 민감
- 성공 기준: recall@3(reranker) ≥ recall@5(baseline)이면 UX상 의미 있음
- `run_eval(label="baseline")` vs `run_eval(label="reranker")`로 나란히 비교 가능

## 구현 위치

- `shared/observability/eval/metrics.py` — `mrr()` 추가
- `shared/observability/eval/evaluator.py` — `eval_ks=[1,3,5]` 파라미터
- `tests/eval/runner.py` — `label` 파라미터 추가, 새 포맷 출력
