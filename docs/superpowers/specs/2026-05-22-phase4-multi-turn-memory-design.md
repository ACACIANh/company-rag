# Phase 4: 멀티턴 메모리 설계 스펙

**Date**: 2026-05-22  
**Goal**: 대화 컨텍스트 유지로 "방금 그 문서 더 자세히" 같은 참조 표현 처리 및 5턴 이상 대화 일관성 구현

---

## 1. 배경 및 현황

Phase 3까지 구현된 내용:
- `MemorySaver` + `thread_id` 인프라 존재 (`builder.py`)
- `AgentState.chat_history: list[dict]` 필드 존재
- **문제**: `answer_question()`이 매 호출 시 `chat_history: []`로 초기화 → 이전 대화 유실

Phase 4가 해결할 것:
- `chat_history`를 세션 간 보존
- 대명사·참조 표현 해소 (`rewrite_query`에서 이전 대화 컨텍스트 활용)
- 토큰 폭증 방지 (최근 10턴만 유지)

---

## 2. 아키텍처

### 2.1 그래프 구조 변경

**Before (Phase 3):**
```
START → rewrite_query → router → [retrieve|web_search|confirm] → generate → check_hallucination → END
```

**After (Phase 4):**
```
START → load_memory → rewrite_query → router → [retrieve|web_search|confirm]
                                                    → generate → check_hallucination → save_memory → END
                                                                         ↓ (환각 재시도)
                                                                      generate
```

- `tool_call` 거부 경로(`confirm → END`)는 save_memory 없이 종료 (답변 없으므로 저장 불필요)
- `route_after_hallucination`의 `"end"` → `"save_memory"`로 변경

### 2.2 상태 흐름

```
[이전 checkpoint] ─── graph.get_state() ──→ answer_question()
                                                    │
                                                    ▼
                                           {question, chat_history(이전)}
                                                    │
                                            START → load_memory (트리밍)
                                                    │
                                            rewrite_query (chat_history 주입)
                                                    │
                                              ... 처리 ...
                                                    │
                                             save_memory (Q&A append)
                                                    │
                                                   END → [새 checkpoint 저장]
```

---

## 3. 새 노드 명세

### 3.1 `load_memory_node`

**파일**: `app/graph/nodes/load_memory.py`

**역할**: 토큰 관리 — chat_history를 최근 N턴으로 트리밍

```python
MAX_TURNS = 10  # 최근 10턴 = 20 메시지 (user + assistant)

def load_memory_node(state: dict) -> dict:
    history = state.get("chat_history", [])
    return {"chat_history": history[-(MAX_TURNS * 2):]}
```

**입력**: `state["chat_history"]`  
**출력**: `{"chat_history": trimmed_list}`  
**비고**: 순수 함수, LLM 호출 없음

### 3.2 `save_memory_node`

**파일**: `app/graph/nodes/save_memory.py`

**역할**: 현재 턴의 Q&A를 chat_history에 append

```python
def save_memory_node(state: dict) -> dict:
    updated = list(state.get("chat_history", [])) + [
        {"role": "user", "content": state["question"]},
        {"role": "assistant", "content": state["answer"]},
    ]
    return {"chat_history": updated}
```

**입력**: `state["chat_history"]`, `state["question"]`, `state["answer"]`  
**출력**: `{"chat_history": appended_list}`  
**비고**: 순수 함수, LLM 호출 없음

---

## 4. 기존 노드/함수 수정

### 4.1 `answer_question()` (`app/graph/builder.py`)

```python
def answer_question(graph, question, config=None):
    config = _ensure_thread_id(config)
    existing = graph.get_state(config)
    chat_history = (existing.values or {}).get("chat_history", [])

    initial: AgentState = {
        "question": question,
        "chat_history": chat_history,   # 이전 대화 보존
        "rewritten_question": "",
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

**변경 핵심**: `graph.get_state(config)`로 이전 checkpoint에서 `chat_history` 로드 후 initial state에 주입.

### 4.2 `build_graph()` (`app/graph/builder.py`)

```python
# 추가 노드
g.add_node("load_memory", load_memory_node)
g.add_node("save_memory", save_memory_node)

# 엣지 변경
g.add_edge(START, "load_memory")         # START → load_memory → rewrite_query
g.add_edge("load_memory", "rewrite_query")

# route_after_hallucination의 "end" → "save_memory"
g.add_conditional_edges(
    "check_hallucination",
    route_after_hallucination,
    {"save_memory": "save_memory", "generate": "generate"},
)
g.add_edge("save_memory", END)
```

### 4.3 `edges.py` — `route_after_hallucination`

```python
def route_after_hallucination(state: dict) -> str:
    if state["hallucination_passed"] or state["retry_count"] >= _MAX_TOTAL_RETRIES:
        return "save_memory"   # "end" → "save_memory"로 변경
    return "generate"
```

### 4.4 `REWRITE_QUERY` 프롬프트 (`app/graph/prompts.py`)

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

### 4.5 `rewrite_query_node` (`app/graph/nodes/rewrite_query.py`)

```python
def rewrite_query_node(state: dict, *, llm: LLMClient) -> dict:
    history = state.get("chat_history", [])
    history_text = "\n".join(
        f"{m['role']}: {m['content']}" for m in history
    ) if history else "없음"
    prompt = REWRITE_QUERY.format(
        question=state["question"],
        chat_history=history_text,
    )
    rewritten = llm.complete(prompt).strip()
    return {"rewritten_question": rewritten}
```

### 4.6 `RAG_GENERATE` 프롬프트 및 `generate_node`

```python
RAG_GENERATE = """\
이전 대화:
{chat_history}

참고 문서:
{context}

질문: {question}
한국어로 답변하세요."""
```

`generate_node`에도 동일하게 `chat_history` 주입.

---

## 5. API 변경 (`app/api/chat.py`)

```python
import uuid as _uuid

class ChatRequest(BaseModel):
    question: str
    session_id: str | None = None  # None이면 새 세션 자동 생성

class ChatResponse(BaseModel):
    answer: str
    sources: list[str]
    session_id: str  # 클라이언트가 다음 요청에 재사용

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    thread_id = req.session_id or str(_uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    result = answer_question(get_graph(), req.question, config=config)
    return ChatResponse(
        answer=result.text,
        sources=result.sources,
        session_id=thread_id,
    )
```

**비고**: `answer_question` 내부에서 이미 `_ensure_thread_id(config)`를 호출하므로 API 레이어는 thread_id를 직접 생성한다. `_ensure_thread_id`는 `builder.py`의 private 함수이므로 API에서 import하지 않는다.

---

## 6. 테스트 전략

| 테스트 | 파일 | 검증 내용 |
|--------|------|-----------|
| `load_memory_node` | `tests/app/graph/nodes/test_load_memory.py` | 트리밍, 빈 배열, 경계값 |
| `save_memory_node` | `tests/app/graph/nodes/test_save_memory.py` | append 정확성, 기존 히스토리 보존 |
| `rewrite_query_node` | `tests/app/graph/nodes/test_rewrite_query.py` | chat_history 주입 확인 (기존 테스트 확장) |
| `generate_node` | `tests/app/graph/nodes/test_generate.py` | chat_history 컨텍스트 주입 확인 |
| `edges.py` | `tests/app/graph/test_edges.py` | route_after_hallucination이 save_memory 반환 확인 |
| `builder.py` 통합 | `tests/app/graph/test_builder.py` | 멀티턴 시나리오 (2턴 이상) |
| `chat.py` API | `tests/app/api/test_chat.py` | session_id 전달/반환 |

---

## 7. Definition of Done

| DoD 항목 | 검증 방법 |
|----------|----------|
| "방금 그 문서 더 자세히" 참조 표현 처리 | 통합 테스트: 2턴 대화, 2턴에서 "그 문서" 참조 → rewrite가 구체화 |
| 동일 세션 5턴 이상 일관성 | `test_builder.py`: 5턴 시나리오, session_id 재사용 |
| 토큰 폭증 없이 운영 | `test_load_memory.py`: MAX_TURNS 초과 시 트리밍 확인 |
| 회귀 테스트 통과 | `tests/eval/runner.py` — Phase 3 recall@5 ≥ 0.80 유지 |
| 기존 단위 테스트 전부 통과 | `pytest tests/ --ignore=tests/eval` |

---

## 8. 파일 맵 (변경/생성)

| 파일 | 작업 |
|------|------|
| `app/graph/nodes/load_memory.py` | **Create** |
| `app/graph/nodes/save_memory.py` | **Create** |
| `app/graph/nodes/rewrite_query.py` | **Modify** (chat_history 주입) |
| `app/graph/nodes/generate.py` | **Modify** (chat_history 주입) |
| `app/graph/prompts.py` | **Modify** (REWRITE_QUERY, RAG_GENERATE) |
| `app/graph/edges.py` | **Modify** (route_after_hallucination "end"→"save_memory") |
| `app/graph/builder.py` | **Modify** (두 노드 추가, answer_question 수정) |
| `app/api/chat.py` | **Modify** (session_id 추가) |
| `tests/app/graph/nodes/test_load_memory.py` | **Create** |
| `tests/app/graph/nodes/test_save_memory.py` | **Create** |
| `tests/app/graph/nodes/test_rewrite_query.py` | **Modify** |
| `tests/app/graph/nodes/test_generate.py` | **Modify** |
| `tests/app/graph/test_edges.py` | **Modify** |
| `tests/app/graph/test_builder.py` | **Modify** |
| `tests/app/api/test_chat.py` | **Modify** |
