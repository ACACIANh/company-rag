# 참조 문서 없음 고지 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `doc_search` 경로에서 관련 문서를 찾지 못했을 때 응답 앞에 명확한 고지문을 표시하고 일반 지식 기반 답변을 제공한다.

**Architecture:** `generate_node`에서 `route == "doc_search"` AND (`documents` 없음 OR `relevance_score < 0.5`) 조건을 감지해 별도 프롬프트로 LLM 호출 후 하드코딩된 고지문을 앞에 붙인다. `check_hallucination_node`는 `documents`가 없으면 즉시 통과시켜 불필요한 retry를 방지한다.

**Tech Stack:** Python 3.11, pytest, unittest.mock

---

## 파일 변경 목록

| 파일 | 변경 |
|------|------|
| `app/graph/nodes/check_hallucination.py` | 수정 — 빈 documents 조기 반환 추가 |
| `app/graph/nodes/generate.py` | 수정 — 문서 없음 분기 로직 추가 |
| `app/graph/prompts.py` | 수정 — `RAG_GENERATE_NO_DOCS` 프롬프트 추가 |
| `tests/app/graph/nodes/test_check_hallucination.py` | 수정 — 빈 documents 테스트 추가 |
| `tests/app/graph/nodes/test_generate.py` | 수정 — 문서 없음/저관련성/정상/web_search 테스트 추가 |

---

### Task 1: `check_hallucination_node` 빈 documents 조기 반환

**Files:**
- Modify: `app/graph/nodes/check_hallucination.py`
- Test: `tests/app/graph/nodes/test_check_hallucination.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/app/graph/nodes/test_check_hallucination.py` 파일 끝에 아래 테스트를 추가한다.

```python
def test_check_hallucination_skips_llm_when_no_documents():
    mock_llm = MagicMock()

    state = {
        "answer": "일반 지식 기반 답변",
        "documents": [],
        "retry_count": 0,
    }
    result = check_hallucination_node(state, llm=mock_llm)

    assert result == {"hallucination_passed": True}
    mock_llm.complete.assert_not_called()
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/app/graph/nodes/test_check_hallucination.py::test_check_hallucination_skips_llm_when_no_documents -v
```

Expected: `FAILED` — `mock_llm.complete` 가 호출되어 `assert_not_called()` 실패

- [ ] **Step 3: `check_hallucination_node` 수정**

`app/graph/nodes/check_hallucination.py` 전체를 아래로 교체한다.

```python
from shared.llm.base import LLMClient
from app.graph.prompts import CHECK_HALLUCINATION


def check_hallucination_node(state: dict, *, llm: LLMClient) -> dict:
    if not state["documents"]:
        return {"hallucination_passed": True}
    context = "\n\n".join(d.chunk.text for d in state["documents"])
    prompt = CHECK_HALLUCINATION.format(context=context, answer=state["answer"])
    response = llm.complete(prompt).strip().upper()
    passed = "YES" in response
    if passed:
        return {"hallucination_passed": True}
    return {"hallucination_passed": False, "retry_count": state["retry_count"] + 1}
```

- [ ] **Step 4: 전체 check_hallucination 테스트 통과 확인**

```bash
pytest tests/app/graph/nodes/test_check_hallucination.py -v
```

Expected: 5개 모두 `PASSED`

- [ ] **Step 5: 커밋**

```bash
git add app/graph/nodes/check_hallucination.py tests/app/graph/nodes/test_check_hallucination.py
git commit -m "feat: check_hallucination_node — documents 없으면 LLM 호출 없이 통과"
```

---

### Task 2: `RAG_GENERATE_NO_DOCS` 프롬프트 추가

**Files:**
- Modify: `app/graph/prompts.py`

- [ ] **Step 1: `prompts.py` 끝에 프롬프트 추가**

`app/graph/prompts.py` 파일 끝에 아래를 추가한다.

```python
RAG_GENERATE_NO_DOCS = """\
이전 대화:
{chat_history}

질문: {question}
사내 문서에서 관련 정보를 찾지 못했습니다. 일반 지식을 바탕으로 한국어로 답변하세요."""
```

- [ ] **Step 2: import 가능한지 확인**

```bash
python -c "from app.graph.prompts import RAG_GENERATE_NO_DOCS; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: 커밋**

```bash
git add app/graph/prompts.py
git commit -m "feat: prompts — RAG_GENERATE_NO_DOCS 프롬프트 추가"
```

---

### Task 3: `generate_node` 문서 없음 분기 구현

**Files:**
- Modify: `app/graph/nodes/generate.py`
- Test: `tests/app/graph/nodes/test_generate.py`

- [ ] **Step 1: 실패 테스트 4개 작성**

`tests/app/graph/nodes/test_generate.py` 파일 끝에 아래 테스트를 추가한다.

```python
_NOTICE_PREFIX = "⚠️ 관련 사내 문서를 찾지 못했습니다."


def test_generate_node_prepends_notice_when_no_documents():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "일반 답변"

    state = {
        "question": "질문",
        "rewritten_question": "질문",
        "documents": [],
        "relevance_score": 0.0,
        "route": "doc_search",
        "chat_history": [],
    }
    result = generate_node(state, llm=mock_llm)

    assert result["answer"].startswith(_NOTICE_PREFIX)
    assert "일반 답변" in result["answer"]
    assert result["citations"] == []


def test_generate_node_prepends_notice_when_low_relevance():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "일반 답변"

    state = {
        "question": "질문",
        "rewritten_question": "질문",
        "documents": [_make_result("내용", "doc.md")],
        "relevance_score": 0.3,
        "route": "doc_search",
        "chat_history": [],
    }
    result = generate_node(state, llm=mock_llm)

    assert result["answer"].startswith(_NOTICE_PREFIX)
    assert "일반 답변" in result["answer"]
    assert result["citations"] == []


def test_generate_node_no_notice_when_relevant_docs_exist():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "문서 기반 답변"

    state = {
        "question": "질문",
        "rewritten_question": "질문",
        "documents": [_make_result("내용", "doc.md")],
        "relevance_score": 0.8,
        "route": "doc_search",
        "chat_history": [],
    }
    result = generate_node(state, llm=mock_llm)

    assert not result["answer"].startswith(_NOTICE_PREFIX)
    assert result["answer"] == "문서 기반 답변"
    assert len(result["citations"]) == 1


def test_generate_node_no_notice_for_web_search_route():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "웹 검색 답변"

    state = {
        "question": "질문",
        "rewritten_question": "질문",
        "documents": [],
        "relevance_score": 0.0,
        "route": "web_search",
        "chat_history": [],
    }
    result = generate_node(state, llm=mock_llm)

    assert not result["answer"].startswith(_NOTICE_PREFIX)
    assert result["answer"] == "웹 검색 답변"
```

- [ ] **Step 2: 테스트 4개 실패 확인**

```bash
pytest tests/app/graph/nodes/test_generate.py::test_generate_node_prepends_notice_when_no_documents \
       tests/app/graph/nodes/test_generate.py::test_generate_node_prepends_notice_when_low_relevance \
       tests/app/graph/nodes/test_generate.py::test_generate_node_no_notice_when_relevant_docs_exist \
       tests/app/graph/nodes/test_generate.py::test_generate_node_no_notice_for_web_search_route -v
```

Expected: 4개 모두 `FAILED`

- [ ] **Step 3: `generate_node` 수정**

`app/graph/nodes/generate.py` 전체를 아래로 교체한다.

```python
from shared.llm.base import LLMClient
from shared.models import SourceRef
from shared.observability.cost_tracker import get_tracker
from app.graph.prompts import RAG_GENERATE, RAG_GENERATE_NO_DOCS

_NO_DOC_NOTICE = (
    "⚠️ 관련 사내 문서를 찾지 못했습니다.\n"
    "일반 지식을 바탕으로 답변드립니다.\n\n---\n\n"
)
_RELEVANCE_THRESHOLD = 0.5


def generate_node(state: dict, *, llm: LLMClient) -> dict:
    question = state.get("rewritten_question") or state["question"]
    history = state.get("chat_history", [])
    history_text = "\n".join(
        f"{m['role']}: {m['content']}" for m in history
    ) if history else "없음"

    is_doc_search = state.get("route") == "doc_search"
    no_relevant_docs = (
        not state["documents"]
        or state.get("relevance_score", 1.0) < _RELEVANCE_THRESHOLD
    )

    if is_doc_search and no_relevant_docs:
        prompt = RAG_GENERATE_NO_DOCS.format(
            chat_history=history_text,
            question=question,
        )
        text = _NO_DOC_NOTICE + llm.complete(prompt)
        citations = []
    else:
        context = "\n\n".join(d.chunk.text for d in state["documents"])
        prompt = RAG_GENERATE.format(
            context=context,
            question=question,
            chat_history=history_text,
        )
        text = llm.complete(prompt)
        citations = [
            SourceRef(
                source=d.chunk.source,
                document_id=d.chunk.metadata.get("document_id", ""),
                sensitivity=d.chunk.metadata.get("sensitivity", "public"),
                team_id=d.chunk.metadata.get("team_id", ""),
            )
            for d in state["documents"]
        ]

    tracker = get_tracker()
    if tracker:
        tracker.track(
            user_id=state.get("user_id", "anonymous"),
            input_tokens=len(prompt) // 4,
            output_tokens=len(text) // 4,
            model="unknown",
        )

    return {"answer": text, "citations": citations}
```

- [ ] **Step 4: 신규 테스트 4개 + 기존 테스트 모두 통과 확인**

```bash
pytest tests/app/graph/nodes/test_generate.py -v
```

Expected: 전체 `PASSED` (기존 6개 + 신규 4개 = 10개)

- [ ] **Step 5: 커밋**

```bash
git add app/graph/nodes/generate.py tests/app/graph/nodes/test_generate.py
git commit -m "feat: generate_node — 문서 없음/저관련성 시 고지문 + 일반 답변 분기"
```

---

### Task 4: 전체 회귀 확인

**Files:** 없음 (실행만)

- [ ] **Step 1: 전체 단위 테스트 실행**

```bash
pytest tests/app/graph/ -v
```

Expected: 전체 `PASSED`, 실패 없음

- [ ] **Step 2: eval 회귀 점수 확인**

```bash
python tests/eval/runner.py
```

Expected: 이전 대비 점수 하락 없음. 하락 시 원인을 PR description에 명시.
