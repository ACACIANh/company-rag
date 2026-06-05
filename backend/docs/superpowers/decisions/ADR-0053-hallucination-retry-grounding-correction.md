# ADR-0053: Self-RAG hallucination 재시도 — grounding 교정 주입

> **Status**: 🟢 적용완료

**Date**: 2026-06-05
**Context**: hallucination 체크 실패 시 라우팅이 `generate → check_hallucination → generate`로 돌지만, `generate_node`가 동일한 `documents`·`question`·프롬프트로 LLM을 재호출했다(`edges.py:route_after_hallucination`, `builder.py` 배선). `LLMClient.complete`에 temperature가 없어 재시도가 사실상 같은 입력의 재호출이라, 환각의 근본 원인(문서 이탈/문서가 답을 안 담음)을 풀지 못하고 LLM 샘플링 노이즈에만 의존했다.

## Options

| 선택지 | 트레이드오프 |
|--------|------------|
| A. 문서화만 (코드 무변경) | 의도된 설계로 명문화. 그러나 동일 입력 재호출 문제는 그대로 — 결국 동작 개선이 필요해져 churn. **기각** |
| B. `generate` 재시도에 grounding 교정 지시 주입 (프롬프트 변주) | 재시도 시 입력이 실제로 바뀜. temperature/ABC 확장 불필요. hallucination 게이트가 잡는 "문서 이탈" 실패 모드를 직접 겨냥. 새 state 필드 불필요. **채택** |
| C. temperature 변주 | `LLMClient.complete` ABC에 temperature 추가 필요(레이어 작업). "문서가 답을 안 담은" 경우는 못 풂. **기각** |
| D. hallucination 실패 → `rewrite_query`/`retrieve` 재배선 | 가장 큰 그래프 변경. `rewrite_query`도 retry-aware가 아니라 같은 질의→같은 문서로 효과 불확실. **기각** |

## Decision

**선택: B — 재시도 시 grounding 교정 지시 주입**

### 구현 세부

**재시도 신호**: `state["answer"]`가 truthy면 = hallucination 재시도(`generate` 재진입). `generate`는 doc_search 경로 전용이고 첫 생성에는 answer가 비어 있으므로, answer 존재 ⟺ 직전 생성이 있었음 ⟺ 재시도다. 새 state 필드를 추가하지 않는다(AgentState TypedDict 무변경).

**`app/graph/prompts.py`** — `REGENERATE_GROUNDING_NOTICE` 신설(RAG_GENERATE 뒤에 덧붙이는 교정 절):
> 직전 답변이 위 문서에 충분히 근거하지 않았습니다. 이번에는 반드시 위 참고 문서의 내용만으로 답하고, 문서에서 확인할 수 없는 내용은 추측하지 말고 "제공된 문서에서 확인할 수 없습니다"라고 답하세요.

**`app/graph/nodes/generate.py`**:
```python
prompt = RAG_GENERATE.format(...)
if state.get("answer"):            # 재시도면 입력을 바꾼다
    prompt += REGENERATE_GROUNDING_NOTICE
text = llm.complete(prompt)
```

## Rationale

- **근본 원인 해소**: hallucination 게이트는 `grade_documents`가 이미 문서 관련성을 통과시킨 뒤 도는 단계다. 실패 원인은 (a) 문서는 관련 있으나 LLM이 이탈, (b) 문서가 답을 안 담음. 교정 절은 (a)면 LLM을 문서로 끌어오고, (b)면 환각 대신 정직한 "확인 불가"를 유도한다 — 두 실패 모드를 모두 처리한다.
- **국소성**: 그래프 배선·카운터·ABC를 건드리지 않는다. `prompts.py` + `generate.py` 두 파일, 프롬프트 변주만으로 "동일 입력 재호출" 루프를 깬다.
- **카운터 계약 보존**: `retry_count` 공유(grade `_MAX_GRADE_RETRIES=2` + hallucination `_MAX_TOTAL_RETRIES=3`)는 의도된 설계(메모리 노트 + `test_edges.py`)이며 본 변경은 카운터 동작을 바꾸지 않는다.

## 대안 기각 이유

- **문서화만 (A)**: "의도된 설계"로 못 박아도 동일 입력 재호출은 비용·지연만 늘리는 부채로 남아, 결국 B/C/D 중 하나로 가게 된다. 미루는 ADR + 바꾸는 ADR 두 번을 쓰는 churn을 피하려 지금 B로 확정한다.
- **temperature (C)**: `LLMClient.complete` ABC 확장(레이어 경계 작업)이 필요하고, "문서가 답을 안 담은" 실패 모드는 샘플링만으로 못 푼다.
- **재배선 (D)**: `rewrite_query`도 retry-aware가 아니라 재진입 시 같은 질의→같은 문서가 될 공산이 커 효과가 불확실하면서 변경 면적은 가장 크다.

## 영향

- **동작 변경**: hallucination 재시도 시 프롬프트가 길어진다(교정 절 추가). 첫 생성은 무변경.
- **AgentState**: 무변경(신호로 기존 `answer` 필드 재사용).
- **후속 과제**: `rewrite_query` 자체의 retry-awareness(grade 재시도 다양성)는 본 ADR 범위 밖.

## 관련

- [ADR-0031](ADR-0031-router-agent-label-permission-routing.md) — 라우터/Self-RAG 흐름 명명 (기각 대안 맥락에서 hallucination 루프 언급)
- `project_self_rag_design.md` (메모리) — retry_count 단일 필드 제어 설계
