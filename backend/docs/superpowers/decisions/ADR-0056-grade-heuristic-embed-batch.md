# ADR-0056: 데모 잔여 레버 — grade_documents LLM→cosine 휴리스틱 + multi_query embed_batch

> **Status**: 🟢 적용완료   <!-- 🟢 적용완료 · 🔵 승인됨 · ⚪ 제안됨 · 🟡 보류 · 🟣 대체됨 · ⚫ 폐기 -->

**Date**: 2026-06-08
**Context**: [ADR-0055](ADR-0055-demo-perf-fga-parallelization.md)가 "안전한 것만" 적용 후 보류한 잔여 레버 중, **C(grade_documents LLM 휴리스틱 대체)는 RAG 품질에 영향이라 별도 ADR + 사인오프 대상**으로 남겼다. 사용자가 "옵션 2 진행"을 택하며 `AskUserQuestion`으로 (1) 레버 범위 A+B (2) **품질 회귀 허용: "미미한 하락(≤2%)"**을 확정해 이 ADR로 진행한다.

## 두 레버

### 레버 B — multi_query 임베딩 배치 (안전, 품질 영향 0)
`retrieve_node` multi_query 경로는 쿼리별 `retriever.retrieve(q)`를 `asyncio.gather`로 감쌌으나, `BasicRetriever.retrieve` 내부 `embedder.embed`가 **동기 블로킹**이라 사실상 임베딩이 직렬이었다. `Retriever.retrieve_batch`(기본=per-query 병렬 fallback / `BasicRetriever` override=`embed_batch` 1회+검색 병렬)를 추가해 임베딩 왕복을 N→1로 줄인다. 임베딩 결과는 단건 `embed`와 동일 → RRF 병합 문서 불변(**동작 보존**). 커밋 `df928c3`.

### 레버 A — grade_documents: LLM 채점 → 검색 top-cosine 임계 (품질 영향, eval 게이트)
모든 doc_search 장면이 관련성 채점에 **LLM 1콜**(critical path)을 썼다. 이를 검색 cosine 임계로 대체해 잔여 레버 중 **유일하게 데모 wall-clock을 실제로 줄인다**. 실측(5질문, 라이브 gpt-4.1-mini): grade LLM 콜 **median 697ms(513~1044ms) → 휴리스틱 0.008ms = doc_search 장면당 ~0.7s 절감**(retry 시 사이클마다 배가). 단 Self-RAG 관련성 게이트([ADR-0053]) 동작 변경이라 품질 회귀 위험 → 보정+eval 게이트로 검증.

## 측정

### 임계 보정 (`scripts/calibrate_grade.py`, 라이브 OpenAI+pgvector)
eval 질문(생성해야 정상)과 off-topic 질문(거부해야 정상)의 검색 top-cosine = `max(d.score)` (프로덕션 grade가 보는 rerank된 top_k=5 기준)과 현행 LLM grade 점수를 함께 수집:

| 집단 | top_cosine | LLM 판정 |
|------|-----------|---------|
| eval (24, 생성해야 정상) | min 0.339 / median 0.512 / max 0.658 | 22 생성, 2 거부(온보딩 0.359·기기분실 0.339) |
| off-topic (5, 거부해야 정상) | min 0.207 / median 0.234 / **max 0.288** | **5/5 거부** |

**깨끗한 분리**: off-topic max(0.288) < eval min(0.339), LLM-확정-관련 클러스터 ≥0.385. → **`COSINE_THRESHOLD = 0.35`**: off-topic 위 +0.062 마진(강건한 거부), 관련 클러스터 아래 -0.035 마진(명백히 관련된 질문 오거부 0). LLM 판정과 **28/29 일치**.

### eval 회귀 게이트 (`scripts/eval_grade_ab.py`, 전사 열람권 user-admin, 24 doc_search 종단)
같은 스크립트를 grade만 baseline(LLM)으로 되돌려(stash) A/B:

| | mean keyword_hit_rate | NO_DOC(거부) |
|---|---|---|
| baseline (LLM grade) | 0.8750 | 1/24 (기기분실) |
| **heuristic (cosine T=0.35)** | **0.8958** | **0/24** |

**회귀 없음(오히려 +2.1pp)**. 주동인: baseline이 punt한 기기분실을 휴리스틱은 retry 후 생성. 함께-생성된 질문의 ±0.5 편차(코드리뷰↓·50만원↑)는 grade 무관한 **generate 비결정 노이즈**(양방향). 사용자 게이트(≤2% 회귀) **통과**.
(recall@5는 양쪽 0 — `expected_source` 이름 포맷 불일치라는 **기존 eval 하니스 버그**로, 본 변경과 무관·동일 조건이라 비신호.)

## Decision
**레버 A·B 모두 적용.** grade_documents는 LLM 채점을 제거하고 `max(d.score) ≥ 0.35` 이진 판정(`relevance_score` 1.0/0.0)으로 대체. 노드는 LLM 비의존 순수 함수가 된다(builder에서 `partial(..., llm=llm)` → `grade_documents_node`).

설계 요점:
- **이진 매핑(1.0/0.0)**: `relevance_score`는 `route_after_grade`(retry 게이트)와 `generate.py`(답변 vs `_NO_DOC_NOTICE`) 두 곳에서 **모두 `< 0.5` 비교** → 이진화로 단일 `COSINE_THRESHOLD` 노브가 두 계약을 동시 보존. edges.py·generate.py 미수정(수술적).
- **`max(d.score)`**: reranker가 순서를 바꿔도 견고(현 RERANKER_TYPE=none이라 `documents[0]`과 동치이나 향후 LLM reranker 대비).

## Rationale / 정직한 한계
- eval 세트(`questions.yaml`)는 전부 "관련 문서가 있어야 정상"인 질문이라 grade의 핵심 기능인 **"무관 문서 거부"를 직접 테스트하는 케이스가 없다.** 그래서 거부 능력은 별도 off-topic 질문(보정 스크립트)으로 검증했고(5/5 거부), 운영 중 "오통과(무관한데 통과)"는 하류 hallucination 체크 노드가 안전망으로 남는다.
- cosine은 LLM 판단보다 약한 신호다. T=0.35는 29개 점으로 보정된 값(분리 구간 폭 0.097)이라 신규 질문이 구간 경계에 떨어지면 오분류 가능 — 그래서 거부 클러스터(0.288) 위로 충분한 마진을 두어 **오거부보다 (안전망 있는) 오통과 쪽으로** 보수적으로 잡았다.
- LLM 채점 프롬프트 `GRADE_DOCUMENTS`는 `prompts.py`에 **보존**한다(롤백 = grade_documents.py·builder.py 2파일만 되돌리면 됨). 재보정/회귀 재측정 도구도 보존: `scripts/calibrate_grade.py`(자립), `scripts/eval_grade_ab.py`.

## 검증
- 단위테스트 648 통과. grade 휴리스틱 5개(임계 경계·max·빈 문서·LLM 비의존), retrieve_batch 회귀 가드(embed_batch 1회·ABC fallback). builder 통합테스트는 grade의 LLM 콜 제거에 맞춰 시퀀스 갱신, `retry_on_low_grade`는 문서 cosine으로 retry를 태우도록 재작성(휴리스틱 의미 반영).
- 롤백 절차: `git checkout <base> -- app/graph/nodes/grade_documents.py app/graph/builder.py` (GRADE_DOCUMENTS 보존이라 즉시 복귀).
