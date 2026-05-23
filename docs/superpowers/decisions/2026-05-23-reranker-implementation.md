# Decision: Reranker 구현체 선택

**Date**: 2026-05-23
**Context**: Reranker 구현체 방식 결정 — 사내 문서를 외부로 보내지 않아야 하고, 사내 LLM 인프라 활용 가능

## Options

| 선택지 | 트레이드오프 |
|--------|------------|
| `sentence-transformers` cross-encoder (로컬 라이브러리) | 무료·빠름·HTTP 없음. 단, 한국어 multilingual 모델 선택 필요, 사내 LLM 활용 불가 |
| 퍼블릭 클라우드 API (Cohere Rerank, Voyage AI 등) | 편리하나 사내 문서가 외부 서버로 전송됨 — **불가** |
| 사내 LLM via OpenAI 호환 HTTP API | 사내 인프라 내 데이터 유지. `base_url`만 바꾸면 전환. 단, 문서당 토큰 소모 |

## Decision

**선택: 사내 LLM via OpenAI 호환 HTTP API (`LLMReranker`)**

## Rationale

- 퍼블릭 클라우드는 사내 문서 보안 정책상 불가
- 사내 LLM이 OpenAI 호환 API로 운영 중 → `base_url`만 교체하면 즉시 연결
- Listwise 방식(단일 API 호출로 전체 문서 재정렬) 채택 — pointwise(문서당 1호출)보다 비용·지연 모두 낮음
- 파싱 실패·API 오류 시 원래 순서 유지 fallback으로 안전성 확보
- 향후 cross-encoder로 교체 시 `Reranker` ABC 구현체만 교체하면 됨 (호출부 변경 없음)

## 설정값

| 파라미터 | 값 | 이유 |
|----------|---|------|
| `retrieve_top_k` | 20 | reranker가 추려낼 pool 크기 |
| `top_k` | 5 | 최종 generate 노드에 전달할 문서 수 |

## 구현 위치

- `shared/reranker/llm_reranker.py` — `LLMReranker` 구현
- `app/graph/nodes/retrieve.py` — retrieve → reranker → cut 파이프라인
- `app/graph/builder.py` — `build_graph(reranker=LLMReranker(...))` 주입

## 전환 방법

```python
# 현재 (OpenAI로 테스트)
client = OpenAI(api_key="...")

# 사내 LLM으로 전환 시
client = OpenAI(api_key="internal-key", base_url="https://사내LLM주소/v1")

reranker = LLMReranker(client, model="사내모델명")
graph = build_graph(retriever=..., llm=..., reranker=reranker)
```
