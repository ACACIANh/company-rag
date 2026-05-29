# 참조 문서 없음 고지 설계

## 개요

`doc_search` 경로에서 관련 문서를 찾지 못했거나 관련성이 낮을 때, 응답 텍스트 앞에 명확한 고지문을 표시하고 일반 지식 기반 답변을 제공한다.

## 동기

현재 `generate_node`는 `documents`가 비어 있거나 `relevance_score`가 낮아도 빈 context로 LLM을 호출한다. LLM이 "문서 없음"을 명시하지 않고 일반 지식으로 답하거나 어색한 답변을 낼 수 있어, 사용자가 응답의 출처를 판단하기 어렵다.

## 범위

- 변경 파일: `app/graph/nodes/generate.py`, `app/graph/prompts.py`, `app/graph/nodes/check_hallucination.py`
- 상태 스키마(`AgentState`) 변경 없음
- 다른 노드·엣지 변경 없음

## 트리거 조건

| 조건 | 고지문 표시 |
|------|------------|
| `route != "doc_search"` (web_search 등) | ❌ |
| `route == "doc_search"` + `documents` 있음 + `relevance_score >= 0.5` | ❌ |
| `route == "doc_search"` + `documents` 없음 | ✅ |
| `route == "doc_search"` + `documents` 있으나 `relevance_score < 0.5` | ✅ |

임계값: `_RELEVANCE_THRESHOLD = 0.5` (`edges.py`의 기존 값과 동일)

## 출력 형식

```
⚠️ 관련 사내 문서를 찾지 못했습니다.
일반 지식을 바탕으로 답변드립니다.

---

[LLM 일반 답변]
```

고지문은 하드코딩된 상수로 결정론적으로 붙임. LLM이 임의로 변경하지 않음.

## 구현 상세

### `app/graph/prompts.py`

기존 `RAG_GENERATE` 외 새 프롬프트 추가:

```python
RAG_GENERATE_NO_DOCS = """\
이전 대화:
{chat_history}

질문: {question}
사내 문서에서 관련 정보를 찾지 못했습니다. 일반 지식을 바탕으로 한국어로 답변하세요."""
```

### `app/graph/nodes/generate.py`

```python
_NO_DOC_NOTICE = (
    "⚠️ 관련 사내 문서를 찾지 못했습니다.\n"
    "일반 지식을 바탕으로 답변드립니다.\n\n---\n\n"
)
_RELEVANCE_THRESHOLD = 0.5
```

`generate_node` 내 분기:

1. `is_doc_search = state.get("route") == "doc_search"`
2. `no_relevant_docs = not state["documents"] or state.get("relevance_score", 1.0) < _RELEVANCE_THRESHOLD`
3. 두 조건 모두 참이면:
   - `RAG_GENERATE_NO_DOCS` 프롬프트 사용 (context 없음)
   - `text = _NO_DOC_NOTICE + llm.complete(prompt)`
   - `citations = []` 반환
4. 아니면 기존 로직 그대로

## 테스트 계획

- `test_generate_node_no_docs`: `documents=[]`, `route="doc_search"` → 고지문 포함 확인
- `test_generate_node_low_relevance`: `documents=[...]`, `relevance_score=0.3`, `route="doc_search"` → 고지문 포함 확인
- `test_generate_node_with_docs`: 정상 경로 → 고지문 미포함 확인
- `test_generate_node_web_search`: `route="web_search"`, `documents=[]` → 고지문 미포함 확인
- `test_check_hallucination_no_docs`: `documents=[]` → `hallucination_passed=True` 즉시 반환 확인

### `app/graph/nodes/check_hallucination.py`

`documents`가 비어 있으면 즉시 `hallucination_passed=True` 반환. 빈 context로 LLM에게 검증을 요청하면 항상 "NO"가 반환돼 `_MAX_TOTAL_RETRIES`까지 불필요한 재시도가 발생하기 때문.

```python
def check_hallucination_node(state, *, llm):
    if not state["documents"]:
        return {"hallucination_passed": True}
    # 기존 로직 그대로
    ...
```

## 영향 분석

- 기존 `doc_search` 정상 경로: 영향 없음
- `web_search` 경로: 영향 없음 (`route != "doc_search"`)
- `tool_call` 경로: 영향 없음
- `ChatResponse.sources`: 빈 리스트 반환 (기존과 동일)
- 할루시네이션 체크: 문서 없음 경로에서는 스킵 (불필요한 retry 제거)
