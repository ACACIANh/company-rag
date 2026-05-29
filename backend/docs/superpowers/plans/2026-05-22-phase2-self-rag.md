# Phase 2: Self-RAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `rewrite_query`, `grade_documents`, `check_hallucination` 세 노드와 조건부 엣지를 추가해 Self-RAG 검증 루프를 구현한다.

**Architecture:** Phase 1의 선형 그래프(`retrieve → generate`)를 `rewrite_query → retrieve → grade_documents →(조건부)→ generate → check_hallucination →(조건부)→ END` 구조로 확장한다. 관련성 부족 시 `increment_retry → rewrite_query` 루프백(최대 2회), 환각 감지 시 `generate` 재시도(최대 1회). `retry_count` 하나로 두 루프의 무한 루프를 방지한다. `AgentState.documents`의 `add` reducer를 제거해 재시도 시 문서가 누적되지 않고 교체되도록 한다.

**Tech Stack:** Python 3.11+, LangGraph, shared.llm.base.LLMClient (ABC), pytest, unittest.mock

---

## 파일 맵

| Task | 생성/수정 |
|---|---|
| Task 1 | Modify: `app/graph/state.py`, `tests/app/graph/test_state.py` |
| Task 2 | Modify: `app/graph/prompts.py` |
| Task 3 | Create: `app/graph/nodes/rewrite_query.py`, `tests/app/graph/nodes/test_rewrite_query.py` |
| Task 4 | Create: `app/graph/nodes/grade_documents.py`, `tests/app/graph/nodes/test_grade_documents.py` |
| Task 5 | Create: `app/graph/nodes/check_hallucination.py`, `tests/app/graph/nodes/test_check_hallucination.py` |
| Task 6 | Create: `app/graph/nodes/increment_retry.py`, `tests/app/graph/nodes/test_increment_retry.py` |
| Task 7 | Modify: `app/graph/nodes/retrieve.py`, `tests/app/graph/nodes/test_retrieve.py` |
| Task 8 | Modify: `app/graph/nodes/generate.py`, `tests/app/graph/nodes/test_generate.py` |
| Task 9 | Modify: `app/graph/edges.py`, Create: `tests/app/graph/test_edges.py` |
| Task 10 | Modify: `app/graph/builder.py`, `tests/app/graph/test_builder.py` |
| Task 11 | Eval: `tests/eval/runner.py` 실행으로 DoD 검증 |

---

### Task 1: AgentState — `documents`에서 add reducer 제거

**배경:** Phase 1의 `Annotated[list[SearchResult], add]`는 병렬 검색을 염두에 둔 설계였으나, Phase 2의 순차적 재시도 루프에서는 이전 검색 결과가 누적되어 오염된다. 이 Task에서 교체 의미론으로 변경한다.

**Files:**
- Modify: `app/graph/state.py`
- Modify: `tests/app/graph/test_state.py`

- [ ] **Step 1: `app/graph/state.py` 수정**

```python
from typing import Literal, TypedDict

from shared.models import SearchResult


class AgentState(TypedDict):
    question: str
    rewritten_question: str
    chat_history: list[dict]
    route: Literal["doc_search", "tool_call", "web_search"]
    documents: list[SearchResult]   # 재시도 시 교체 (add reducer 제거)
    relevance_score: float
    retry_count: int
    answer: str
    citations: list[str]
    hallucination_passed: bool
```

- [ ] **Step 2: `tests/app/graph/test_state.py`에 documents 타입 테스트 추가**

파일 끝에 아래 테스트를 추가한다 (기존 2개 테스트는 유지):

```python
from typing import get_type_hints
from app.graph.state import AgentState


def test_documents_is_plain_list_not_annotated():
    from typing import get_args, get_origin
    import typing
    hints = get_type_hints(AgentState, include_extras=True)
    doc_hint = hints["documents"]
    # Annotated[..., add]가 아닌 순수 list 타입이어야 함
    assert get_origin(doc_hint) is list or doc_hint is list or str(doc_hint).startswith("list")
```

- [ ] **Step 3: 테스트 실행**

```bash
pytest tests/app/graph/test_state.py -v
```

Expected: 3 PASSED

- [ ] **Step 4: 전체 기존 테스트 통과 확인**

```bash
pytest tests/ -q --ignore=tests/eval
```

Expected: 전부 PASS (기존 100개 + 새 1개)

- [ ] **Step 5: Commit**

```bash
git add app/graph/state.py tests/app/graph/test_state.py
git commit -m "refactor(state): remove add reducer from documents for sequential Self-RAG retry"
```

---

### Task 2: 새 프롬프트 3개를 `app/graph/prompts.py`에 추가

**Files:**
- Modify: `app/graph/prompts.py`

- [ ] **Step 1: `app/graph/prompts.py` 전체를 다음으로 교체**

```python
RAG_GENERATE = "context:\n{context}\n\nquestion: {question}\nanswer in Korean."

REWRITE_QUERY = """\
다음 질문을 사내 문서 검색에 최적화되도록 재작성하세요.
모호한 대명사를 명시적 명사로 풀고, 핵심 키워드를 포함하세요.
재작성된 질문만 출력하세요.

원본 질문: {question}
재작성된 질문:"""

GRADE_DOCUMENTS = """\
다음 문서들이 질문에 관련이 있는지 평가하고 관련성 점수를 출력하세요.
0.0(전혀 관련 없음)부터 1.0(매우 관련 있음) 사이의 숫자만 출력하세요.

질문: {question}

문서:
{context}

관련성 점수 (숫자만):"""

CHECK_HALLUCINATION = """\
다음 답변이 제공된 문서의 내용에만 근거하는지 검증하세요.
문서에 근거한 답변이면 YES, 문서에 없는 내용이 포함되어 있으면 NO로만 답하세요.

문서:
{context}

답변: {answer}

검증 결과 (YES 또는 NO):"""
```

- [ ] **Step 2: import 확인**

```bash
python3 -c "from app.graph.prompts import RAG_GENERATE, REWRITE_QUERY, GRADE_DOCUMENTS, CHECK_HALLUCINATION; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/graph/prompts.py
git commit -m "feat(prompts): add REWRITE_QUERY, GRADE_DOCUMENTS, CHECK_HALLUCINATION templates"
```

---

### Task 3: `rewrite_query_node`

**Files:**
- Create: `app/graph/nodes/rewrite_query.py`
- Create: `tests/app/graph/nodes/test_rewrite_query.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/app/graph/nodes/test_rewrite_query.py`:

```python
from unittest.mock import MagicMock

from app.graph.nodes.rewrite_query import rewrite_query_node


def test_rewrite_query_returns_rewritten_question():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "재작성된 질문"

    state = {"question": "그거 어떻게 해?"}
    result = rewrite_query_node(state, llm=mock_llm)

    assert result == {"rewritten_question": "재작성된 질문"}


def test_rewrite_query_strips_whitespace():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "  연차 신청 방법  \n"

    state = {"question": "연차 어떻게 써?"}
    result = rewrite_query_node(state, llm=mock_llm)

    assert result["rewritten_question"] == "연차 신청 방법"


def test_rewrite_query_includes_original_in_prompt():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "재작성"

    rewrite_query_node({"question": "원본 질문"}, llm=mock_llm)

    prompt = mock_llm.complete.call_args[0][0]
    assert "원본 질문" in prompt
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/app/graph/nodes/test_rewrite_query.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.graph.nodes.rewrite_query'`

- [ ] **Step 3: `app/graph/nodes/rewrite_query.py` 구현**

```python
from shared.llm.base import LLMClient
from app.graph.prompts import REWRITE_QUERY


def rewrite_query_node(state: dict, *, llm: LLMClient) -> dict:
    prompt = REWRITE_QUERY.format(question=state["question"])
    rewritten = llm.complete(prompt).strip()
    return {"rewritten_question": rewritten}
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/app/graph/nodes/test_rewrite_query.py -v
```

Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add app/graph/nodes/rewrite_query.py tests/app/graph/nodes/test_rewrite_query.py
git commit -m "feat(nodes): add rewrite_query_node"
```

---

### Task 4: `grade_documents_node`

**Files:**
- Create: `app/graph/nodes/grade_documents.py`
- Create: `tests/app/graph/nodes/test_grade_documents.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/app/graph/nodes/test_grade_documents.py`:

```python
from unittest.mock import MagicMock

from shared.models import Chunk, SearchResult
from app.graph.nodes.grade_documents import grade_documents_node


def _make_result(text: str) -> SearchResult:
    return SearchResult(chunk=Chunk(text=text, source="a.md", chunk_id="c1"), score=0.9)


def test_grade_documents_returns_float_score():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "0.8"

    state = {
        "rewritten_question": "연차 신청 방법",
        "documents": [_make_result("연차는 15일입니다.")],
    }
    result = grade_documents_node(state, llm=mock_llm)

    assert "relevance_score" in result
    assert abs(result["relevance_score"] - 0.8) < 1e-6


def test_grade_documents_falls_back_to_zero_on_invalid_response():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "잘 모르겠어요"

    state = {
        "rewritten_question": "질문",
        "documents": [_make_result("내용")],
    }
    result = grade_documents_node(state, llm=mock_llm)

    assert result["relevance_score"] == 0.0


def test_grade_documents_empty_documents_returns_zero():
    mock_llm = MagicMock()

    state = {"rewritten_question": "질문", "documents": []}
    result = grade_documents_node(state, llm=mock_llm)

    assert result["relevance_score"] == 0.0
    mock_llm.complete.assert_not_called()


def test_grade_documents_includes_question_and_context_in_prompt():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "0.9"

    state = {
        "rewritten_question": "검색 질문",
        "documents": [_make_result("핵심 문서 내용")],
    }
    grade_documents_node(state, llm=mock_llm)

    prompt = mock_llm.complete.call_args[0][0]
    assert "검색 질문" in prompt
    assert "핵심 문서 내용" in prompt
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/app/graph/nodes/test_grade_documents.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: `app/graph/nodes/grade_documents.py` 구현**

```python
import re

from shared.llm.base import LLMClient
from app.graph.prompts import GRADE_DOCUMENTS


def grade_documents_node(state: dict, *, llm: LLMClient) -> dict:
    if not state["documents"]:
        return {"relevance_score": 0.0}
    context = "\n\n".join(d.chunk.text for d in state["documents"])
    prompt = GRADE_DOCUMENTS.format(question=state["rewritten_question"], context=context)
    response = llm.complete(prompt).strip()
    match = re.search(r"([01](?:\.\d+)?)", response)
    score = float(match.group(1)) if match else 0.0
    return {"relevance_score": min(max(score, 0.0), 1.0)}
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/app/graph/nodes/test_grade_documents.py -v
```

Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add app/graph/nodes/grade_documents.py tests/app/graph/nodes/test_grade_documents.py
git commit -m "feat(nodes): add grade_documents_node with regex score parsing"
```

---

### Task 5: `check_hallucination_node`

**Files:**
- Create: `app/graph/nodes/check_hallucination.py`
- Create: `tests/app/graph/nodes/test_check_hallucination.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/app/graph/nodes/test_check_hallucination.py`:

```python
from unittest.mock import MagicMock

from shared.models import Chunk, SearchResult
from app.graph.nodes.check_hallucination import check_hallucination_node


def _make_result(text: str) -> SearchResult:
    return SearchResult(chunk=Chunk(text=text, source="a.md", chunk_id="c1"), score=0.9)


def test_check_hallucination_passes_when_llm_says_yes():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "YES"

    state = {
        "answer": "연차는 15일입니다.",
        "documents": [_make_result("연차는 15일입니다.")],
        "retry_count": 0,
    }
    result = check_hallucination_node(state, llm=mock_llm)

    assert result["hallucination_passed"] is True
    assert "retry_count" not in result


def test_check_hallucination_fails_when_llm_says_no_and_increments_retry():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "NO"

    state = {
        "answer": "임의의 답변",
        "documents": [_make_result("다른 내용")],
        "retry_count": 1,
    }
    result = check_hallucination_node(state, llm=mock_llm)

    assert result["hallucination_passed"] is False
    assert result["retry_count"] == 2


def test_check_hallucination_is_case_insensitive():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "yes, this answer is grounded"

    state = {
        "answer": "답변",
        "documents": [_make_result("근거")],
        "retry_count": 0,
    }
    result = check_hallucination_node(state, llm=mock_llm)

    assert result["hallucination_passed"] is True


def test_check_hallucination_includes_answer_and_context_in_prompt():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "YES"

    state = {
        "answer": "검증 대상 답변",
        "documents": [_make_result("참조 문서")],
        "retry_count": 0,
    }
    check_hallucination_node(state, llm=mock_llm)

    prompt = mock_llm.complete.call_args[0][0]
    assert "검증 대상 답변" in prompt
    assert "참조 문서" in prompt
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/app/graph/nodes/test_check_hallucination.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: `app/graph/nodes/check_hallucination.py` 구현**

```python
from shared.llm.base import LLMClient
from app.graph.prompts import CHECK_HALLUCINATION


def check_hallucination_node(state: dict, *, llm: LLMClient) -> dict:
    context = "\n\n".join(d.chunk.text for d in state["documents"])
    prompt = CHECK_HALLUCINATION.format(context=context, answer=state["answer"])
    response = llm.complete(prompt).strip().upper()
    passed = "YES" in response
    if passed:
        return {"hallucination_passed": True}
    return {"hallucination_passed": False, "retry_count": state["retry_count"] + 1}
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/app/graph/nodes/test_check_hallucination.py -v
```

Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add app/graph/nodes/check_hallucination.py tests/app/graph/nodes/test_check_hallucination.py
git commit -m "feat(nodes): add check_hallucination_node (increments retry_count on fail)"
```

---

### Task 6: `increment_retry_node`

**Files:**
- Create: `app/graph/nodes/increment_retry.py`
- Create: `tests/app/graph/nodes/test_increment_retry.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/app/graph/nodes/test_increment_retry.py`:

```python
from app.graph.nodes.increment_retry import increment_retry_node


def test_increment_retry_increments_count():
    result = increment_retry_node({"retry_count": 0})
    assert result == {"retry_count": 1}


def test_increment_retry_increments_from_nonzero():
    result = increment_retry_node({"retry_count": 1})
    assert result == {"retry_count": 2}
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/app/graph/nodes/test_increment_retry.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: `app/graph/nodes/increment_retry.py` 구현**

```python
def increment_retry_node(state: dict) -> dict:
    return {"retry_count": state["retry_count"] + 1}
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/app/graph/nodes/test_increment_retry.py -v
```

Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
git add app/graph/nodes/increment_retry.py tests/app/graph/nodes/test_increment_retry.py
git commit -m "feat(nodes): add increment_retry_node"
```

---

### Task 7: `retrieve_node` — `rewritten_question` 우선 사용

**배경:** Phase 2에서 `rewrite_query_node`가 `rewritten_question`을 설정한다. `retrieve_node`는 이 값을 우선적으로 사용하고, 없으면 `question`으로 폴백해야 한다.

**Files:**
- Modify: `app/graph/nodes/retrieve.py`
- Modify: `tests/app/graph/nodes/test_retrieve.py`

- [ ] **Step 1: `tests/app/graph/nodes/test_retrieve.py`에 테스트 추가**

기존 파일 끝에 아래 테스트 2개를 추가한다 (기존 테스트 2개는 유지):

```python
def test_retrieve_node_uses_rewritten_question_when_available():
    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value = []

    retrieve_node(
        {"question": "원본 질문", "rewritten_question": "재작성 질문"},
        retriever=mock_retriever,
    )

    mock_retriever.retrieve.assert_called_once_with("재작성 질문", top_k=5)


def test_retrieve_node_falls_back_to_question_when_rewritten_empty():
    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value = []

    retrieve_node(
        {"question": "원본 질문", "rewritten_question": ""},
        retriever=mock_retriever,
    )

    mock_retriever.retrieve.assert_called_once_with("원본 질문", top_k=5)
```

- [ ] **Step 2: 새 테스트 실패 확인**

```bash
pytest tests/app/graph/nodes/test_retrieve.py -v
```

Expected: 기존 2개 PASS, 새 2개 FAIL

- [ ] **Step 3: `app/graph/nodes/retrieve.py` 수정**

```python
from shared.models import SearchResult
from shared.retriever.base import Retriever


def retrieve_node(state: dict, *, retriever: Retriever) -> dict:
    query = state.get("rewritten_question") or state["question"]
    results: list[SearchResult] = retriever.retrieve(query, top_k=5)
    return {"documents": results}
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/app/graph/nodes/test_retrieve.py -v
```

Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add app/graph/nodes/retrieve.py tests/app/graph/nodes/test_retrieve.py
git commit -m "feat(nodes): retrieve_node prefers rewritten_question over question"
```

---

### Task 8: `generate_node` — `rewritten_question` 우선 사용

**Files:**
- Modify: `app/graph/nodes/generate.py`
- Modify: `tests/app/graph/nodes/test_generate.py`

- [ ] **Step 1: `tests/app/graph/nodes/test_generate.py`에 테스트 추가**

기존 파일 끝에 아래 테스트를 추가한다 (기존 테스트 2개는 유지):

```python
def test_generate_node_uses_rewritten_question_in_prompt():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "답변"

    state = {
        "question": "원본 질문",
        "rewritten_question": "재작성된 질문",
        "documents": [_make_result("문서 내용", "doc.md")],
    }
    generate_node(state, llm=mock_llm)

    prompt = mock_llm.complete.call_args[0][0]
    assert "재작성된 질문" in prompt
    assert "원본 질문" not in prompt


def test_generate_node_falls_back_to_question_when_rewritten_empty():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "답변"

    state = {
        "question": "원본 질문",
        "rewritten_question": "",
        "documents": [_make_result("내용", "doc.md")],
    }
    generate_node(state, llm=mock_llm)

    prompt = mock_llm.complete.call_args[0][0]
    assert "원본 질문" in prompt
```

- [ ] **Step 2: 새 테스트 실패 확인**

```bash
pytest tests/app/graph/nodes/test_generate.py -v
```

Expected: 기존 2개 PASS, 새 2개 FAIL

- [ ] **Step 3: `app/graph/nodes/generate.py` 수정**

```python
from shared.llm.base import LLMClient
from app.graph.prompts import RAG_GENERATE


def generate_node(state: dict, *, llm: LLMClient) -> dict:
    question = state.get("rewritten_question") or state["question"]
    context = "\n\n".join(d.chunk.text for d in state["documents"])
    prompt = RAG_GENERATE.format(context=context, question=question)
    text = llm.complete(prompt)
    citations = [d.chunk.source for d in state["documents"]]
    return {"answer": text, "citations": citations}
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/app/graph/nodes/test_generate.py -v
```

Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add app/graph/nodes/generate.py tests/app/graph/nodes/test_generate.py
git commit -m "feat(nodes): generate_node prefers rewritten_question over question"
```

---

### Task 9: `edges.py` — 조건부 라우팅 함수

**설계:**
- `route_after_grade`: `relevance_score >= 0.5` 이거나 `retry_count >= 2`이면 `"generate"`, 아니면 `"rewrite_retry"`
- `route_after_hallucination`: `hallucination_passed`이거나 `retry_count >= 3`이면 `"end"`, 아니면 `"generate"`
- `retry_count` 한계값 근거: grade 루프 최대 2회(`retry_count` 0→1→2), hallucination 루프 최대 1회(grade 0~2회 후 3에 도달하면 종료)

**Files:**
- Modify: `app/graph/edges.py`
- Create: `tests/app/graph/test_edges.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/app/graph/test_edges.py`:

```python
from app.graph.edges import route_after_grade, route_after_hallucination


# ─── route_after_grade ───

def test_route_after_grade_goes_to_generate_when_score_high():
    state = {"relevance_score": 0.8, "retry_count": 0}
    assert route_after_grade(state) == "generate"


def test_route_after_grade_goes_to_generate_at_threshold():
    state = {"relevance_score": 0.5, "retry_count": 0}
    assert route_after_grade(state) == "generate"


def test_route_after_grade_retries_when_score_low_and_count_below_limit():
    state = {"relevance_score": 0.3, "retry_count": 0}
    assert route_after_grade(state) == "rewrite_retry"


def test_route_after_grade_retries_once_more_at_count_1():
    state = {"relevance_score": 0.1, "retry_count": 1}
    assert route_after_grade(state) == "rewrite_retry"


def test_route_after_grade_forces_generate_when_retry_limit_reached():
    state = {"relevance_score": 0.0, "retry_count": 2}
    assert route_after_grade(state) == "generate"


# ─── route_after_hallucination ───

def test_route_after_hallucination_ends_when_passed():
    state = {"hallucination_passed": True, "retry_count": 0}
    assert route_after_hallucination(state) == "end"


def test_route_after_hallucination_retries_when_failed_and_count_below_limit():
    state = {"hallucination_passed": False, "retry_count": 0}
    assert route_after_hallucination(state) == "generate"


def test_route_after_hallucination_ends_when_retry_limit_reached():
    state = {"hallucination_passed": False, "retry_count": 3}
    assert route_after_hallucination(state) == "end"


def test_route_after_hallucination_ends_after_two_grade_retries_and_one_halluc_retry():
    # grade 2회 + hallucination 1회 → retry_count=3 → 종료
    state = {"hallucination_passed": False, "retry_count": 3}
    assert route_after_hallucination(state) == "end"
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/app/graph/test_edges.py -v
```

Expected: `ImportError` (edges.py가 플레이스홀더라 route_after_grade 없음)

- [ ] **Step 3: `app/graph/edges.py` 구현**

```python
_RELEVANCE_THRESHOLD = 0.5
_MAX_GRADE_RETRIES = 2
_MAX_TOTAL_RETRIES = 3


def route_after_grade(state: dict) -> str:
    if state["relevance_score"] >= _RELEVANCE_THRESHOLD or state["retry_count"] >= _MAX_GRADE_RETRIES:
        return "generate"
    return "rewrite_retry"


def route_after_hallucination(state: dict) -> str:
    if state["hallucination_passed"] or state["retry_count"] >= _MAX_TOTAL_RETRIES:
        return "end"
    return "generate"
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/app/graph/test_edges.py -v
```

Expected: 9 PASSED

- [ ] **Step 5: Commit**

```bash
git add app/graph/edges.py tests/app/graph/test_edges.py
git commit -m "feat(edges): add route_after_grade and route_after_hallucination"
```

---

### Task 10: `builder.py` — Self-RAG 그래프 조립

**그래프 구조:**
```
START → rewrite_query → retrieve → grade_documents
grade_documents →(route_after_grade)→ "generate" | "rewrite_retry"
rewrite_retry(increment_retry) → rewrite_query  ← 루프
generate → check_hallucination
check_hallucination →(route_after_hallucination)→ "end" | "generate"
```

**Files:**
- Modify: `app/graph/builder.py`
- Modify: `tests/app/graph/test_builder.py`

- [ ] **Step 1: `tests/app/graph/test_builder.py`에 Self-RAG 테스트 추가**

기존 파일 끝에 아래 테스트들을 추가한다 (기존 테스트 2개는 유지):

```python
def test_answer_question_self_rag_happy_path():
    """rewrite → retrieve → grade(pass) → generate → hallucination(pass) → END"""
    retriever = _make_retriever(text="연차는 15일입니다.", source="vacation.md")
    llm = MagicMock()
    llm.complete.side_effect = [
        "연차 신청 방법",   # rewrite_query
        "0.9",             # grade_documents
        "정답",            # generate
        "YES",             # check_hallucination
    ]
    graph = build_graph(retriever=retriever, llm=llm)
    result = answer_question(graph, "연차 어떻게 써?")

    assert result.text == "정답"
    assert "vacation.md" in result.sources


def test_answer_question_retries_on_low_grade_then_passes():
    """grade(fail) → increment_retry → rewrite → retrieve → grade(pass) → generate → hallucination(pass) → END"""
    retriever = _make_retriever(text="내용", source="doc.md")
    llm = MagicMock()
    llm.complete.side_effect = [
        "첫 재작성",   # rewrite_query (initial)
        "0.2",         # grade_documents (fail → rewrite_retry)
        "두 번째 재작성",  # rewrite_query (retry)
        "0.8",         # grade_documents (pass → generate)
        "좋은 답변",   # generate
        "YES",         # check_hallucination
    ]
    graph = build_graph(retriever=retriever, llm=llm)
    result = answer_question(graph, "원본 질문")

    assert result.text == "좋은 답변"


def test_answer_question_retries_generate_on_hallucination_fail():
    """hallucination(fail) → generate → hallucination(pass) → END"""
    retriever = _make_retriever(text="문서", source="doc.md")
    llm = MagicMock()
    llm.complete.side_effect = [
        "재작성",   # rewrite_query
        "0.9",      # grade_documents (pass)
        "첫 답변",  # generate (hallucination will fail)
        "NO",       # check_hallucination (fail → retry generate)
        "두 번째 답변",  # generate (retry)
        "YES",      # check_hallucination (pass)
    ]
    graph = build_graph(retriever=retriever, llm=llm)
    result = answer_question(graph, "질문")

    assert result.text == "두 번째 답변"
```

- [ ] **Step 2: 새 테스트 실패 확인**

```bash
pytest tests/app/graph/test_builder.py -v
```

Expected: 기존 2개 PASS, 새 3개 FAIL (`ImportError` 또는 그래프 구조 불일치)

- [ ] **Step 3: `app/graph/builder.py` 전체 교체**

```python
from functools import partial

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from shared.llm.base import LLMClient
from shared.models import Answer
from shared.retriever.base import Retriever
from app.graph.edges import route_after_grade, route_after_hallucination
from app.graph.nodes.check_hallucination import check_hallucination_node
from app.graph.nodes.generate import generate_node
from app.graph.nodes.grade_documents import grade_documents_node
from app.graph.nodes.increment_retry import increment_retry_node
from app.graph.nodes.retrieve import retrieve_node
from app.graph.nodes.rewrite_query import rewrite_query_node
from app.graph.state import AgentState


def build_graph(retriever: Retriever, llm: LLMClient) -> CompiledStateGraph:
    g = StateGraph(AgentState)

    g.add_node("rewrite_query", partial(rewrite_query_node, llm=llm))
    g.add_node("retrieve", partial(retrieve_node, retriever=retriever))
    g.add_node("grade_documents", partial(grade_documents_node, llm=llm))
    g.add_node("increment_retry", increment_retry_node)
    g.add_node("generate", partial(generate_node, llm=llm))
    g.add_node("check_hallucination", partial(check_hallucination_node, llm=llm))

    g.add_edge(START, "rewrite_query")
    g.add_edge("rewrite_query", "retrieve")
    g.add_edge("retrieve", "grade_documents")
    g.add_edge("increment_retry", "rewrite_query")
    g.add_edge("generate", "check_hallucination")

    g.add_conditional_edges(
        "grade_documents",
        route_after_grade,
        {"generate": "generate", "rewrite_retry": "increment_retry"},
    )
    g.add_conditional_edges(
        "check_hallucination",
        route_after_hallucination,
        {"end": END, "generate": "generate"},
    )

    return g.compile()


def answer_question(graph: CompiledStateGraph, question: str) -> Answer:
    initial: AgentState = {
        "question": question,
        "rewritten_question": "",
        "chat_history": [],
        "route": "doc_search",
        "documents": [],
        "relevance_score": 0.0,
        "retry_count": 0,
        "answer": "",
        "citations": [],
        "hallucination_passed": False,
    }
    final = graph.invoke(initial)
    return Answer(text=final["answer"], sources=final["citations"])
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/app/graph/test_builder.py -v
```

Expected: 5 PASSED

- [ ] **Step 5: 전체 테스트 통과 확인**

```bash
pytest tests/ -q --ignore=tests/eval
```

Expected: 전부 PASS (새 노드 테스트 포함)

- [ ] **Step 6: Commit**

```bash
git add app/graph/builder.py tests/app/graph/test_builder.py
git commit -m "feat(builder): wire Self-RAG graph with rewrite/grade/hallucination loop"
```

---

### Task 11: 평가셋 실행 — Phase 2 DoD 검증

**목표:** Phase 1 베이스라인(recall@5=0.60) 대비 10% 이상 향상 확인.

**전제:** 벡터 DB와 LLM API 키(.env)가 설정되어 있어야 한다.

- [ ] **Step 1: 평가 스크립트 작성 및 실행**

아래 명령으로 직접 실행:

```bash
python3 - <<'PY'
from app.graph.builder import answer_question, build_graph
from shared.config import load_config
from shared.embedder import SentenceTransformerEmbedder
from shared.llm.factory import create_llm
from shared.retriever import BasicRetriever
from shared.vector_store.factory import create_vector_store
from tests.eval.runner import run_eval

config = load_config()
embedder = SentenceTransformerEmbedder(config.embedding_model)
store = create_vector_store(config)
retriever = BasicRetriever(store=store, embedder=embedder)
llm = create_llm(config)
graph = build_graph(retriever=retriever, llm=llm)

run_eval(lambda q: answer_question(graph, q))
PY
```

- [ ] **Step 2: 결과 기록**

`plan/plan.md`의 Phase 2 DoD 섹션에 결과를 기록한다:

```markdown
- [ ] Phase 1 평가셋에서 정답률 10% 이상 향상
  - 측정 결과: recall@5=X.XX (Phase 1: 0.60) / keyword_hit=X.XX (2026-05-22)
  - 취약 질문: ...
```

- [ ] **Step 3: 결과 커밋**

```bash
git add plan/plan.md
git commit -m "docs(plan): record Phase 2 eval results"
```

---

## Self-Review 체크

**Spec 커버리지:**
- ✅ `rewrite_query` 노드 (Task 3)
- ✅ `grade_documents` 노드 — 관련성 0~1 채점 (Task 4)
- ✅ `check_hallucination` 노드 (Task 5)
- ✅ 조건부 엣지 — grade 결과 기반 rewrite 루프백 최대 2회 (Task 9)
- ✅ 조건부 엣지 — 환각 감지 시 generate 루프백 최대 1회 (Task 9)
- ✅ `retry_count` 무한 루프 방지 (Tasks 6, 5, 9)
- ✅ 평가셋 정답률 10% 향상 확인 (Task 11)
- ✅ LangSmith 트레이싱 — 기존 연동 유지, 루프백 시각화 자동 반영

**Placeholder 없음:** ✅ 모든 스텝에 실제 코드 포함

**타입 일관성:**
- `rewrite_query_node` → `{"rewritten_question": str}` → `retrieve_node`에서 `state.get("rewritten_question")` ✅
- `grade_documents_node` → `{"relevance_score": float}` → `route_after_grade`에서 `state["relevance_score"]` ✅
- `check_hallucination_node` → `{"hallucination_passed": bool, "retry_count": int}` → `route_after_hallucination`에서 `state["hallucination_passed"]` ✅
- `increment_retry_node` → `{"retry_count": int}` ✅
