# Phase 4: 멀티턴 메모리 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `load_memory_node` + `save_memory_node`를 그래프에 추가하고 `rewrite_query`/`generate`에 chat_history를 주입해 세션 간 대화 컨텍스트를 유지한다.

**Architecture:** `answer_question()`이 `graph.get_state(config)`로 이전 checkpoint에서 chat_history를 로드한다. 그래프 시작부의 `load_memory_node`가 토큰 관리(최근 10턴 트리밍), 끝부의 `save_memory_node`가 Q&A 쌍을 축적한다. `rewrite_query`와 `generate` 프롬프트에 chat_history를 주입해 "방금 그 문서" 같은 참조 표현을 해소한다.

**Tech Stack:** Python 3.11+, LangGraph (MemorySaver checkpointer), pytest, unittest.mock

---

## 파일 맵

| Task | 생성/수정 |
|---|---|
| Task 1 | Create: `app/graph/nodes/load_memory.py`, `tests/app/graph/nodes/test_load_memory.py` |
| Task 2 | Create: `app/graph/nodes/save_memory.py`, `tests/app/graph/nodes/test_save_memory.py` |
| Task 3 | Modify: `app/graph/prompts.py`, `app/graph/nodes/rewrite_query.py`, `tests/app/graph/nodes/test_rewrite_query.py` |
| Task 4 | Modify: `app/graph/nodes/generate.py`, `tests/app/graph/nodes/test_generate.py` |
| Task 5 | Modify: `app/graph/edges.py`, `tests/app/graph/test_edges.py` |
| Task 6 | Modify: `app/graph/builder.py`, `tests/app/graph/test_builder.py` |
| Task 7 | Modify: `app/api/chat.py`, `tests/app/api/test_chat.py` |
| Task 8 | Eval: `tests/eval/runner.py` 실행으로 DoD 회귀 검증 |

---

### Task 1: `load_memory_node` — 히스토리 트리밍

**역할**: 그래프 시작 시 chat_history를 최근 10턴(20 메시지)으로 트리밍. 순수 함수, LLM 호출 없음.

**Files:**
- Create: `app/graph/nodes/load_memory.py`
- Create: `tests/app/graph/nodes/test_load_memory.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/app/graph/nodes/test_load_memory.py`:

```python
from app.graph.nodes.load_memory import load_memory_node, MAX_TURNS


def test_load_memory_returns_empty_when_no_history():
    result = load_memory_node({"chat_history": []})
    assert result == {"chat_history": []}


def test_load_memory_preserves_history_within_limit():
    history = [{"role": "user", "content": f"q{i}"} for i in range(5)]
    result = load_memory_node({"chat_history": history})
    assert result == {"chat_history": history}


def test_load_memory_trims_to_max_turns():
    # MAX_TURNS=10 → 20 메시지까지 허용
    history = [{"role": "user", "content": f"q{i}"} for i in range(25)]
    result = load_memory_node({"chat_history": history})
    assert len(result["chat_history"]) == MAX_TURNS * 2
    # 가장 오래된 메시지가 잘려야 함
    assert result["chat_history"][0]["content"] == "q5"
    assert result["chat_history"][-1]["content"] == "q24"


def test_load_memory_handles_missing_chat_history_key():
    result = load_memory_node({})
    assert result == {"chat_history": []}


def test_load_memory_trims_exactly_at_boundary():
    # 정확히 MAX_TURNS * 2 개 → 트리밍 없음
    history = [{"role": "user", "content": f"q{i}"} for i in range(MAX_TURNS * 2)]
    result = load_memory_node({"chat_history": history})
    assert len(result["chat_history"]) == MAX_TURNS * 2
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/app/graph/nodes/test_load_memory.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.graph.nodes.load_memory'`

- [ ] **Step 3: 구현**

`app/graph/nodes/load_memory.py`:

```python
MAX_TURNS = 10


def load_memory_node(state: dict) -> dict:
    history = state.get("chat_history", [])
    return {"chat_history": history[-(MAX_TURNS * 2):]}
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/app/graph/nodes/test_load_memory.py -v
```

Expected: 5 PASSED

- [ ] **Step 5: 전체 기존 테스트 통과 확인**

```bash
pytest tests/ -q --ignore=tests/eval
```

Expected: 전부 PASS

- [ ] **Step 6: Commit**

```bash
git add app/graph/nodes/load_memory.py tests/app/graph/nodes/test_load_memory.py
git commit -m "feat(nodes): add load_memory_node with MAX_TURNS trimming"
```

---

### Task 2: `save_memory_node` — Q&A 축적

**역할**: 그래프 끝에서 현재 턴의 question/answer를 chat_history에 append. 순수 함수, LLM 호출 없음.

**Files:**
- Create: `app/graph/nodes/save_memory.py`
- Create: `tests/app/graph/nodes/test_save_memory.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/app/graph/nodes/test_save_memory.py`:

```python
from app.graph.nodes.save_memory import save_memory_node


def test_save_memory_appends_qa_pair_to_empty_history():
    state = {"question": "연차 어떻게 써?", "answer": "15일입니다.", "chat_history": []}
    result = save_memory_node(state)

    assert result == {
        "chat_history": [
            {"role": "user", "content": "연차 어떻게 써?"},
            {"role": "assistant", "content": "15일입니다."},
        ]
    }


def test_save_memory_appends_to_existing_history():
    existing = [
        {"role": "user", "content": "이전 질문"},
        {"role": "assistant", "content": "이전 답변"},
    ]
    state = {"question": "새 질문", "answer": "새 답변", "chat_history": existing}
    result = save_memory_node(state)

    assert len(result["chat_history"]) == 4
    assert result["chat_history"][0]["content"] == "이전 질문"
    assert result["chat_history"][-1] == {"role": "assistant", "content": "새 답변"}


def test_save_memory_does_not_mutate_original_history():
    original = [{"role": "user", "content": "q"}]
    state = {"question": "new", "answer": "ans", "chat_history": original}
    save_memory_node(state)
    assert len(original) == 1


def test_save_memory_handles_missing_chat_history_key():
    state = {"question": "질문", "answer": "답변"}
    result = save_memory_node(state)
    assert len(result["chat_history"]) == 2
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/app/graph/nodes/test_save_memory.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.graph.nodes.save_memory'`

- [ ] **Step 3: 구현**

`app/graph/nodes/save_memory.py`:

```python
def save_memory_node(state: dict) -> dict:
    updated = list(state.get("chat_history", [])) + [
        {"role": "user", "content": state["question"]},
        {"role": "assistant", "content": state["answer"]},
    ]
    return {"chat_history": updated}
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/app/graph/nodes/test_save_memory.py -v
```

Expected: 4 PASSED

- [ ] **Step 5: 전체 기존 테스트 통과 확인**

```bash
pytest tests/ -q --ignore=tests/eval
```

Expected: 전부 PASS

- [ ] **Step 6: Commit**

```bash
git add app/graph/nodes/save_memory.py tests/app/graph/nodes/test_save_memory.py
git commit -m "feat(nodes): add save_memory_node that appends Q&A pair to chat_history"
```

---

### Task 3: 프롬프트 + `rewrite_query_node` — chat_history 주입

**역할**: `REWRITE_QUERY` 템플릿에 `{chat_history}` 플레이스홀더를 추가하고, `rewrite_query_node`가 이를 포맷해 LLM에 전달함으로써 "방금 그 문서" 같은 참조 표현을 해소한다.

**Files:**
- Modify: `app/graph/prompts.py`
- Modify: `app/graph/nodes/rewrite_query.py`
- Modify: `tests/app/graph/nodes/test_rewrite_query.py`

- [ ] **Step 1: `test_rewrite_query.py`에 실패 테스트 추가**

기존 3개 테스트는 유지하고, 파일 끝에 아래 2개를 추가한다.

```python
def test_rewrite_query_includes_chat_history_in_prompt():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "연차 신청 방법 상세 설명"

    history = [
        {"role": "user", "content": "연차 어떻게 써?"},
        {"role": "assistant", "content": "15일입니다."},
    ]
    state = {"question": "더 자세히", "chat_history": history}
    rewrite_query_node(state, llm=mock_llm)

    prompt = mock_llm.complete.call_args[0][0]
    assert "연차 어떻게 써?" in prompt
    assert "15일입니다." in prompt


def test_rewrite_query_shows_empty_when_no_history():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "재작성"

    state = {"question": "질문", "chat_history": []}
    rewrite_query_node(state, llm=mock_llm)

    prompt = mock_llm.complete.call_args[0][0]
    assert "없음" in prompt
```

- [ ] **Step 2: 새 테스트 실패 확인**

```bash
pytest tests/app/graph/nodes/test_rewrite_query.py -v
```

Expected: 기존 3개 PASS, 새 2개 FAIL (`AssertionError` — 현재 프롬프트에 history 없음)

- [ ] **Step 3: `app/graph/prompts.py`의 `REWRITE_QUERY` 수정**

`app/graph/prompts.py`에서 `REWRITE_QUERY` 상수를 다음으로 교체한다 (나머지 상수는 그대로 유지):

```python
REWRITE_QUERY = """\
다음 질문을 사내 문서 검색에 최적화되도록 재작성하세요.
모호한 대명사를 명시적 명사로 풀고, 핵심 키워드를 포함하세요.
이전 대화를 참고해 참조 표현("그 문서", "방금 그것" 등)을 구체적인 내용으로 해소하세요.
재작성된 질문만 출력하세요.

이전 대화:
{chat_history}

원본 질문: {question}
재작성된 질문:"""
```

- [ ] **Step 4: `app/graph/nodes/rewrite_query.py` 수정**

```python
from shared.llm.base import LLMClient
from app.graph.prompts import REWRITE_QUERY


def rewrite_query_node(state: dict, *, llm: LLMClient) -> dict:
    history = state.get("chat_history", [])
    history_text = "\n".join(
        f"{m['role']}: {m['content']}" for m in history
    ) if history else "없음"
    prompt = REWRITE_QUERY.format(question=state["question"], chat_history=history_text)
    rewritten = llm.complete(prompt).strip()
    return {"rewritten_question": rewritten}
```

- [ ] **Step 5: 전체 `test_rewrite_query.py` 통과 확인**

```bash
pytest tests/app/graph/nodes/test_rewrite_query.py -v
```

Expected: 5 PASSED

- [ ] **Step 6: 전체 테스트 통과 확인**

```bash
pytest tests/ -q --ignore=tests/eval
```

Expected: 전부 PASS

- [ ] **Step 7: Commit**

```bash
git add app/graph/prompts.py app/graph/nodes/rewrite_query.py tests/app/graph/nodes/test_rewrite_query.py
git commit -m "feat(nodes): inject chat_history into rewrite_query for pronoun resolution"
```

---

### Task 4: `generate_node` — chat_history 컨텍스트 추가

**역할**: `RAG_GENERATE` 프롬프트에 이전 대화를 포함해 generate_node가 대화 맥락을 인식한다.

**Files:**
- Modify: `app/graph/prompts.py`
- Modify: `app/graph/nodes/generate.py`
- Modify: `tests/app/graph/nodes/test_generate.py`

- [ ] **Step 1: `test_generate.py`에 실패 테스트 추가**

기존 4개 테스트는 유지하고, 파일 끝에 아래 1개를 추가한다.

```python
def test_generate_node_includes_chat_history_in_prompt():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "답변"

    history = [{"role": "user", "content": "이전 대화 내용"}]
    state = {
        "question": "질문",
        "rewritten_question": "재작성",
        "documents": [_make_result("문서", "doc.md")],
        "chat_history": history,
    }
    generate_node(state, llm=mock_llm)

    prompt = mock_llm.complete.call_args[0][0]
    assert "이전 대화 내용" in prompt
```

- [ ] **Step 2: 새 테스트 실패 확인**

```bash
pytest tests/app/graph/nodes/test_generate.py::test_generate_node_includes_chat_history_in_prompt -v
```

Expected: FAIL (`AssertionError`)

- [ ] **Step 3: `app/graph/prompts.py`의 `RAG_GENERATE` 수정**

`app/graph/prompts.py`에서 `RAG_GENERATE` 상수를 다음으로 교체한다:

```python
RAG_GENERATE = """\
이전 대화:
{chat_history}

참고 문서:
{context}

질문: {question}
한국어로 답변하세요."""
```

- [ ] **Step 4: `app/graph/nodes/generate.py` 수정**

```python
from shared.llm.base import LLMClient
from app.graph.prompts import RAG_GENERATE


def generate_node(state: dict, *, llm: LLMClient) -> dict:
    question = state.get("rewritten_question") or state["question"]
    context = "\n\n".join(d.chunk.text for d in state["documents"])
    history = state.get("chat_history", [])
    history_text = "\n".join(
        f"{m['role']}: {m['content']}" for m in history
    ) if history else "없음"
    prompt = RAG_GENERATE.format(context=context, question=question, chat_history=history_text)
    text = llm.complete(prompt)
    citations = [d.chunk.source for d in state["documents"]]
    return {"answer": text, "citations": citations}
```

- [ ] **Step 5: 전체 `test_generate.py` 통과 확인**

```bash
pytest tests/app/graph/nodes/test_generate.py -v
```

Expected: 5 PASSED

- [ ] **Step 6: 전체 테스트 통과 확인**

```bash
pytest tests/ -q --ignore=tests/eval
```

Expected: 전부 PASS

- [ ] **Step 7: Commit**

```bash
git add app/graph/prompts.py app/graph/nodes/generate.py tests/app/graph/nodes/test_generate.py
git commit -m "feat(nodes): inject chat_history into generate_node prompt"
```

---

### Task 5: `edges.py` — `route_after_hallucination`을 `"save_memory"`로 변경

**역할**: hallucination 통과 또는 재시도 한계 도달 시 `"end"` 대신 `"save_memory"`를 반환해 Q&A를 저장하도록 한다.

**Files:**
- Modify: `app/graph/edges.py`
- Modify: `tests/app/graph/test_edges.py`

- [ ] **Step 1: `test_edges.py`에서 기존 3개 테스트 수정**

`tests/app/graph/test_edges.py`에서 아래 3개 함수를 수정한다 (함수명 + assert 값 변경):

```python
# 변경 전 → 변경 후

def test_route_after_hallucination_ends_when_passed():
    state = {"hallucination_passed": True, "retry_count": 0}
    assert route_after_hallucination(state) == "end"

# ↓↓↓

def test_route_after_hallucination_goes_to_save_memory_when_passed():
    state = {"hallucination_passed": True, "retry_count": 0}
    assert route_after_hallucination(state) == "save_memory"


# 변경 전 → 변경 후

def test_route_after_hallucination_ends_when_retry_limit_reached():
    state = {"hallucination_passed": False, "retry_count": 3}
    assert route_after_hallucination(state) == "end"

# ↓↓↓

def test_route_after_hallucination_goes_to_save_memory_when_retry_limit_reached():
    state = {"hallucination_passed": False, "retry_count": 3}
    assert route_after_hallucination(state) == "save_memory"


# 변경 전 → 변경 후

def test_route_after_hallucination_ends_after_two_grade_retries_and_one_halluc_retry():
    state = {"hallucination_passed": False, "retry_count": 3}
    assert route_after_hallucination(state) == "end"

# ↓↓↓

def test_route_after_hallucination_goes_to_save_memory_after_max_retries():
    state = {"hallucination_passed": False, "retry_count": 3}
    assert route_after_hallucination(state) == "save_memory"
```

- [ ] **Step 2: 수정된 테스트 실패 확인**

```bash
pytest tests/app/graph/test_edges.py -v
```

Expected: 수정된 3개 FAIL (`"end" != "save_memory"`), 나머지 PASS

- [ ] **Step 3: `app/graph/edges.py`의 `route_after_hallucination` 수정**

`app/graph/edges.py`에서 `route_after_hallucination` 함수를 다음으로 교체한다 (다른 함수는 그대로):

```python
def route_after_hallucination(state: dict) -> str:
    if state["hallucination_passed"] or state["retry_count"] >= _MAX_TOTAL_RETRIES:
        return "save_memory"
    return "generate"
```

- [ ] **Step 4: 전체 `test_edges.py` 통과 확인**

```bash
pytest tests/app/graph/test_edges.py -v
```

Expected: 전부 PASS

- [ ] **Step 5: 전체 테스트 확인 (builder 테스트 실패 예상)**

```bash
pytest tests/ -q --ignore=tests/eval
```

Expected: `test_builder.py` 일부 FAIL — builder가 아직 `"save_memory"` 노드를 모르기 때문. Task 6에서 수정.

- [ ] **Step 6: Commit**

```bash
git add app/graph/edges.py tests/app/graph/test_edges.py
git commit -m "feat(edges): route_after_hallucination returns save_memory instead of end"
```

---

### Task 6: `builder.py` — 새 노드 배선 + `answer_question` 멀티턴 지원

**역할**: `load_memory`, `save_memory` 노드를 그래프에 추가하고, `answer_question()`이 이전 checkpoint에서 chat_history를 로드하도록 수정한다.

**Files:**
- Modify: `app/graph/builder.py`
- Modify: `tests/app/graph/test_builder.py`

- [ ] **Step 1: `test_builder.py`에 멀티턴 테스트 추가**

기존 테스트는 그대로 유지하고, 파일 끝에 아래 2개를 추가한다.

```python
def test_answer_question_multi_turn_accumulates_chat_history():
    """2턴 대화 시 chat_history가 누적되고 2턴 rewrite_query 프롬프트에 1턴 질문이 포함된다."""
    retriever = _make_retriever(text="연차는 15일", source="vacation.md")
    llm = MagicMock()
    llm.complete.side_effect = [
        # Turn 1: load_memory(pure) → rewrite → router → retrieve → grade → generate → halluc → save(pure)
        "연차 신청 방법",       # rewrite_query
        "doc_search",          # router
        "0.9",                 # grade_documents
        "연차는 15일입니다.",   # generate
        "YES",                 # check_hallucination
        # Turn 2: 동일 순서
        "연차 상세 설명",       # rewrite_query (should receive history from turn 1)
        "doc_search",          # router
        "0.9",                 # grade_documents
        "더 자세히 설명하면.", # generate
        "YES",                 # check_hallucination
    ]
    graph = build_graph(retriever=retriever, llm=llm)
    config = {"configurable": {"thread_id": "multi-turn-test-1"}}

    result1 = answer_question(graph, "연차 어떻게 써?", config=config)
    assert result1.text == "연차는 15일입니다."

    result2 = answer_question(graph, "더 자세히 알려줘", config=config)
    assert result2.text == "더 자세히 설명하면."

    # 2턴 rewrite_query 프롬프트(6번째 LLM 호출, index=5)에 1턴 질문이 있어야 함
    rewrite_prompt_turn2 = llm.complete.call_args_list[5][0][0]
    assert "연차 어떻게 써?" in rewrite_prompt_turn2


def test_answer_question_new_session_starts_with_empty_history():
    """다른 thread_id는 이전 대화에 접근할 수 없다."""
    retriever = _make_retriever(text="문서", source="doc.md")
    llm = MagicMock()
    llm.complete.side_effect = [
        "연차 신청 방법",  # rewrite_query
        "doc_search",     # router
        "0.9",            # grade_documents
        "정답",           # generate
        "YES",            # check_hallucination
    ]
    graph = build_graph(retriever=retriever, llm=llm)
    # 새 세션 ID — 이전 대화 없음
    config = {"configurable": {"thread_id": "brand-new-session-999"}}
    result = answer_question(graph, "연차 어떻게 써?", config=config)
    assert result.text == "정답"

    # rewrite_query 프롬프트에 "없음"이 포함되어야 함 (빈 히스토리)
    rewrite_prompt = llm.complete.call_args_list[0][0][0]
    assert "없음" in rewrite_prompt
```

- [ ] **Step 2: 새 테스트 실패 확인**

```bash
pytest tests/app/graph/test_builder.py::test_answer_question_multi_turn_accumulates_chat_history -v
pytest tests/app/graph/test_builder.py::test_answer_question_new_session_starts_with_empty_history -v
```

Expected: FAIL (`KeyError` 또는 그래프 구조 오류 — `save_memory` 노드가 없음)

- [ ] **Step 3: `app/graph/builder.py` 전체 교체**

```python
import uuid
from functools import partial

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from shared.llm.base import LLMClient
from shared.models import Answer
from shared.retriever.base import Retriever
from app.graph.edges import (
    route_after_confirm,
    route_after_grade,
    route_after_hallucination,
    route_after_router,
)
from app.graph.nodes.check_hallucination import check_hallucination_node
from app.graph.nodes.confirm import confirm_node
from app.graph.nodes.generate import generate_node
from app.graph.nodes.grade_documents import grade_documents_node
from app.graph.nodes.increment_retry import increment_retry_node
from app.graph.nodes.load_memory import load_memory_node
from app.graph.nodes.retrieve import retrieve_node
from app.graph.nodes.rewrite_query import rewrite_query_node
from app.graph.nodes.router import router_node
from app.graph.nodes.save_memory import save_memory_node
from app.graph.nodes.tool_executor import tool_executor_node
from app.graph.nodes.web_search import web_search_node
from app.graph.state import AgentState


def build_graph(
    retriever: Retriever,
    llm: LLMClient,
    web_search_retriever: Retriever | None = None,
) -> CompiledStateGraph:
    g = StateGraph(AgentState)

    g.add_node("load_memory", load_memory_node)
    g.add_node("rewrite_query", partial(rewrite_query_node, llm=llm))
    g.add_node("router", partial(router_node, llm=llm))
    g.add_node("retrieve", partial(retrieve_node, retriever=retriever))
    g.add_node("grade_documents", partial(grade_documents_node, llm=llm))
    g.add_node("increment_retry", increment_retry_node)
    g.add_node("web_search", partial(web_search_node, retriever=web_search_retriever))
    g.add_node("confirm", confirm_node)
    g.add_node("tool_executor", tool_executor_node)
    g.add_node("generate", partial(generate_node, llm=llm))
    g.add_node("check_hallucination", partial(check_hallucination_node, llm=llm))
    g.add_node("save_memory", save_memory_node)

    # 공통 진입: START → load_memory → rewrite_query → router
    g.add_edge(START, "load_memory")
    g.add_edge("load_memory", "rewrite_query")
    g.add_edge("rewrite_query", "router")

    # 라우터 → 세 경로 분기
    g.add_conditional_edges(
        "router",
        route_after_router,
        {"doc_search": "retrieve", "web_search": "web_search", "tool_call": "confirm"},
    )

    # doc_search 경로 (Self-RAG 루프)
    g.add_edge("retrieve", "grade_documents")
    g.add_edge("increment_retry", "rewrite_query")
    g.add_conditional_edges(
        "grade_documents",
        route_after_grade,
        {"generate": "generate", "rewrite_retry": "increment_retry"},
    )

    # tool_call 경로
    g.add_conditional_edges(
        "confirm",
        route_after_confirm,
        {"tool_executor": "tool_executor", "end": END},
    )
    g.add_edge("tool_executor", "generate")

    # web_search 경로
    g.add_edge("web_search", "generate")

    # 공통 꼬리: generate → check_hallucination → save_memory → END
    g.add_edge("generate", "check_hallucination")
    g.add_conditional_edges(
        "check_hallucination",
        route_after_hallucination,
        {"save_memory": "save_memory", "generate": "generate"},
    )
    g.add_edge("save_memory", END)

    return g.compile(checkpointer=MemorySaver())


def _ensure_thread_id(config: dict | None) -> dict:
    if config is None:
        return {"configurable": {"thread_id": str(uuid.uuid4())}}
    if "configurable" not in config:
        return {**config, "configurable": {"thread_id": str(uuid.uuid4())}}
    if "thread_id" not in config["configurable"]:
        return {**config, "configurable": {**config["configurable"], "thread_id": str(uuid.uuid4())}}
    return config


def answer_question(
    graph: CompiledStateGraph,
    question: str,
    config: dict | None = None,
) -> Answer:
    config = _ensure_thread_id(config)
    existing = graph.get_state(config)
    chat_history = (existing.values or {}).get("chat_history", [])

    initial: AgentState = {
        "question": question,
        "rewritten_question": "",
        "chat_history": chat_history,
        "route": "doc_search",
        "documents": [],
        "relevance_score": 0.0,
        "retry_count": 0,
        "answer": "",
        "citations": [],
        "hallucination_passed": False,
        "confirmed": False,
        "tool_input": "",
    }
    final = graph.invoke(initial, config=config)
    return Answer(text=final["answer"], sources=final["citations"])
```

- [ ] **Step 4: 전체 `test_builder.py` 통과 확인**

```bash
pytest tests/app/graph/test_builder.py -v
```

Expected: 전부 PASS (기존 7개 + 새 2개 = 9개)

- [ ] **Step 5: 전체 테스트 통과 확인**

```bash
pytest tests/ -q --ignore=tests/eval
```

Expected: 전부 PASS

- [ ] **Step 6: Commit**

```bash
git add app/graph/builder.py tests/app/graph/test_builder.py
git commit -m "feat(builder): wire load_memory/save_memory nodes, answer_question loads chat_history from checkpoint"
```

---

### Task 7: `app/api/chat.py` — session_id 추가

**역할**: 클라이언트가 `session_id`를 전달해 동일 세션을 유지하거나, 생략 시 새 세션을 자동 생성한다. 응답에 항상 `session_id`를 포함해 클라이언트가 다음 요청에 재사용할 수 있게 한다.

**Files:**
- Modify: `app/api/chat.py`
- Modify: `tests/app/api/test_chat.py`

- [ ] **Step 1: `test_chat.py`에 실패 테스트 추가**

기존 2개 테스트는 유지하고, 파일 끝에 아래 3개를 추가한다.

```python
def test_chat_response_includes_session_id():
    mock_answer = Answer(text="답변", sources=["doc.md"])
    with patch("app.api.chat.answer_question", return_value=mock_answer), \
         patch("app.api.chat.get_graph", return_value=MagicMock()):
        from app.api.chat import app
        client = TestClient(app)
        data = client.post("/chat", json={"question": "질문"}).json()
    assert "session_id" in data
    assert isinstance(data["session_id"], str)
    assert len(data["session_id"]) > 0


def test_chat_uses_provided_session_id():
    mock_answer = Answer(text="답변", sources=[])
    with patch("app.api.chat.answer_question", return_value=mock_answer) as mock_aq, \
         patch("app.api.chat.get_graph", return_value=MagicMock()):
        from app.api.chat import app
        client = TestClient(app)
        data = client.post("/chat", json={"question": "질문", "session_id": "my-session-123"}).json()
    assert data["session_id"] == "my-session-123"
    # answer_question이 올바른 config로 호출되었는지 확인
    call_config = mock_aq.call_args[1]["config"]
    assert call_config["configurable"]["thread_id"] == "my-session-123"


def test_chat_generates_new_session_id_when_not_provided():
    mock_answer = Answer(text="답변", sources=[])
    with patch("app.api.chat.answer_question", return_value=mock_answer) as mock_aq, \
         patch("app.api.chat.get_graph", return_value=MagicMock()):
        from app.api.chat import app
        client = TestClient(app)
        resp1 = client.post("/chat", json={"question": "q1"}).json()
        resp2 = client.post("/chat", json={"question": "q2"}).json()
    # session_id가 없으면 매 요청마다 새 UUID 생성
    assert resp1["session_id"] != resp2["session_id"]
```

- [ ] **Step 2: 새 테스트 실패 확인**

```bash
pytest tests/app/api/test_chat.py -v
```

Expected: 기존 2개 PASS, 새 3개 FAIL (`KeyError: 'session_id'` 또는 assertion 오류)

- [ ] **Step 3: `app/api/chat.py` 전체 교체**

```python
import uuid
from functools import lru_cache

from fastapi import FastAPI
from pydantic import BaseModel

from shared.config import load_config
from shared.embedder import SentenceTransformerEmbedder
from shared.llm.factory import create_llm
from shared.retriever import BasicRetriever
from shared.vector_store.factory import create_vector_store
from app.graph.builder import answer_question, build_graph

app = FastAPI()


class ChatRequest(BaseModel):
    question: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[str]
    session_id: str


@lru_cache(maxsize=1)
def get_graph():
    config = load_config()
    embedder = SentenceTransformerEmbedder(config.embedding_model)
    store = create_vector_store(config)
    retriever = BasicRetriever(store=store, embedder=embedder)
    llm = create_llm(config)
    return build_graph(retriever=retriever, llm=llm)


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    thread_id = req.session_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    result = answer_question(get_graph(), req.question, config=config)
    return ChatResponse(answer=result.text, sources=result.sources, session_id=thread_id)
```

- [ ] **Step 4: 전체 `test_chat.py` 통과 확인**

```bash
pytest tests/app/api/test_chat.py -v
```

Expected: 5 PASSED

- [ ] **Step 5: 전체 테스트 통과 확인**

```bash
pytest tests/ -q --ignore=tests/eval
```

Expected: 전부 PASS

- [ ] **Step 6: Commit**

```bash
git add app/api/chat.py tests/app/api/test_chat.py
git commit -m "feat(api): add session_id to ChatRequest/ChatResponse for multi-turn session tracking"
```

---

### Task 8: 회귀 평가 — Phase 3 점수 유지 확인

**목표**: Phase 3 recall@5 ≥ 0.80 유지 확인 (DoD 항목).

**전제**: 벡터 DB와 LLM API 키(`.env`)가 설정되어 있어야 한다.

- [ ] **Step 1: 평가 실행**

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

`plan/plan.md`의 Phase 4 DoD 섹션을 아래와 같이 업데이트한다:

```markdown
**Definition of Done**
- [x] "방금 그 문서 더 자세히" 같은 참조 표현 처리 가능 — rewrite_query에 chat_history 주입, test_builder 멀티턴 테스트로 검증 (2026-05-22)
- [x] 동일 세션 내 5턴 이상 대화 일관성 유지 — MemorySaver + save_memory_node로 chat_history 누적 (2026-05-22)
- [x] 토큰 폭증 없이 운영 가능 — load_memory_node가 최근 10턴(20 메시지)으로 트리밍 (2026-05-22)
- [x] 회귀 테스트 통과 — recall@5=X.XX (Phase 3: 0.80 이상 유지 목표), (2026-05-22)
```

- [ ] **Step 3: plan.md 커밋**

```bash
git add plan/plan.md
git commit -m "docs(plan): record Phase 4 DoD results"
```

---

## Self-Review 체크

**Spec 커버리지:**
- ✅ `load_memory_node` — 최근 10턴 트리밍 (Task 1)
- ✅ `save_memory_node` — Q&A 쌍 append (Task 2)
- ✅ `rewrite_query_node` — chat_history 주입으로 참조 표현 해소 (Task 3)
- ✅ `generate_node` — chat_history 컨텍스트 주입 (Task 4)
- ✅ `route_after_hallucination` — "end" → "save_memory" (Task 5)
- ✅ `build_graph` — 두 노드 배선, START→load_memory 경로, save_memory→END (Task 6)
- ✅ `answer_question` — `graph.get_state()`로 chat_history 로드 (Task 6)
- ✅ API session_id — ChatRequest/ChatResponse 확장 (Task 7)
- ✅ 회귀 평가 (Task 8)

**타입 일관성:**
- `load_memory_node` 반환: `{"chat_history": list[dict]}` → `AgentState.chat_history` ✅
- `save_memory_node` 반환: `{"chat_history": list[dict]}` — `list(state.get(...))` 으로 원본 불변 ✅
- `rewrite_query_node` 프롬프트 format: `{question}` + `{chat_history}` — 두 플레이스홀더 모두 `REWRITE_QUERY`에 존재 ✅
- `generate_node` 프롬프트 format: `{context}` + `{question}` + `{chat_history}` — `RAG_GENERATE`에 존재 ✅
- `route_after_hallucination` 반환값 `"save_memory"` → `build_graph`의 conditional_edges dict key `"save_memory"` ✅
- `answer_question` 내 `(existing.values or {})` — `StateSnapshot.values`가 `{}` 또는 실제 state dict인 경우 모두 처리 ✅

**Placeholder 없음**: ✅ 모든 스텝에 실제 코드 포함
