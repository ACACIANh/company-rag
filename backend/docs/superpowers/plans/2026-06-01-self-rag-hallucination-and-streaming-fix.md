# 환각 오탐 & 스트리밍 중복 출력 수정 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** generate/check 프롬프트 목표 정렬로 환각 오탐을 없애고, 스트리밍 시 확정된 최종 답변만 1회 방출해 중복 출력을 제거한다.

**Architecture:** ① `RAG_GENERATE`에 groundedness 제약을 넣어 부풀림을 원천 억제하고 `CHECK_HALLUCINATION`은 사실 주장 기준으로 명확화(둘 다 프롬프트 상수만 수정). ② `generate_node`에서 `token_queue` 방출 로직을 제거하고, `stream_answer`가 그래프 종료 후 확정된 최종 answer를 토큰 청크로 흘린다. 환각 판정 효과는 실제 LLM 평가 스크립트로 측정한다.

**Tech Stack:** Python 3.11+, LangGraph, pytest, OpenAI/Anthropic SDK. 작업 디렉토리: `backend/`. 인터프리터: `.venv/bin/python`. 브랜치: `fix/self-rag-hallucination-overcorrection`.

설계 근거: `docs/superpowers/specs/2026-06-01-self-rag-hallucination-and-streaming-fix-design.md`

---

## File Structure

- `app/graph/nodes/generate.py` — 큐 방출 로직 제거, 항상 `llm.complete()` (Task 1)
- `app/graph/builder.py` — `stream_answer`가 최종 answer를 토큰 청크로 방출 (Task 2)
- `app/graph/prompts.py` — `RAG_GENERATE`(Task 3), `CHECK_HALLUCINATION`(Task 4) 수정
- `tests/eval/eval_hallucination.py` — 신규, 실제 LLM 환각 판정 회귀 측정 (Task 5)
- 테스트: `tests/app/graph/nodes/test_generate.py`(Task 1), `tests/app/graph/test_builder.py`(Task 2), `tests/app/graph/test_prompts.py`(신규, Task 3·4)

---

## Task 1: generate_node 큐 방출 로직 제거 (②-a)

**Files:**
- Modify: `app/graph/nodes/generate.py`
- Test: `tests/app/graph/nodes/test_generate.py`

`generate_node`가 더 이상 `token_queue`에 토큰을 흘리지 않게 한다. 항상 `llm.complete()`로 answer만 생성. no-doc 고지문도 큐 put 없이 반환만. (스트리밍은 Task 2에서 `stream_answer`가 담당.) `config` 파라미터는 LangGraph 노드 시그니처 호환을 위해 유지하되 사용하지 않는다.

- [ ] **Step 1: 큐 검증 단위 테스트 제거**

`tests/app/graph/nodes/test_generate.py`에서 `test_generate_node_streams_tokens_to_queue` 함수(아래 전체)를 삭제한다. generate_node는 더 이상 큐에 토큰을 흘리지 않으므로 이 테스트는 무의미해진다.

```python
@pytest.mark.asyncio
async def test_generate_node_streams_tokens_to_queue():
    """token_queue 있을 때 llm.stream() 호출, 토큰이 큐에 쌓인다."""

    async def _fake_stream(prompt):
        for t in ["안녕", "하세요"]:
            yield t

    mock_llm = MagicMock()
    mock_llm.stream = _fake_stream

    queue: asyncio.Queue = asyncio.Queue()
    state = {
        "question": "질문",
        "rewritten_question": "질문",
        "documents": [_make_result("내용", "doc.md")],
        "relevance_score": 0.9,
        "route": "doc_search",
        "chat_history": [],
    }
    config = {"configurable": {"token_queue": queue}}

    result = await generate_node(state, config=config, llm=mock_llm)

    tokens = []
    while not queue.empty():
        tokens.append(queue.get_nowait())

    assert tokens == [
        {"type": "token", "content": "안녕"},
        {"type": "token", "content": "하세요"},
    ]
    assert result["answer"] == "안녕하세요"
    assert len(result["citations"]) == 1
```

- [ ] **Step 2: 큐가 있어도 complete만 쓰는 것을 검증하는 테스트 추가**

같은 파일 끝에 추가. token_queue가 config에 있어도 generate_node가 `llm.stream`을 호출하지 않고 `llm.complete`만 쓰며, 큐에 아무것도 넣지 않음을 검증한다.

```python
@pytest.mark.asyncio
async def test_generate_node_never_streams_to_queue():
    """token_queue가 있어도 큐에 흘리지 않고 complete만 쓴다 (스트리밍은 stream_answer 담당)."""
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "최종 답변"
    mock_llm.stream = MagicMock(side_effect=AssertionError("stream을 호출하면 안 된다"))

    queue: asyncio.Queue = asyncio.Queue()
    state = {
        "question": "질문",
        "rewritten_question": "질문",
        "documents": [_make_result("내용", "doc.md")],
        "relevance_score": 0.9,
        "route": "doc_search",
        "chat_history": [],
    }
    config = {"configurable": {"token_queue": queue}}

    result = await generate_node(state, config=config, llm=mock_llm)

    assert result["answer"] == "최종 답변"
    assert queue.empty()
    mock_llm.complete.assert_called_once()
```

- [ ] **Step 3: 테스트 실행 — 실패 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/nodes/test_generate.py::test_generate_node_never_streams_to_queue -v`
Expected: FAIL — 현재 generate_node가 queue에 토큰을 넣으므로 `queue.empty()`가 False (또는 stream 호출로 AssertionError).

- [ ] **Step 4: generate_node 구현 변경**

`app/graph/nodes/generate.py` 전체를 아래로 교체한다. `import asyncio` 제거, 큐 분기 제거, no-doc 고지문도 put 없이 반환, 본문은 `llm.complete()`만.

```python
from langchain_core.runnables import RunnableConfig

from core.llm.base import LLMClient
from core.models import SourceRef
from core.observability.cost_tracker import get_tracker
from app.graph.prompts import RAG_GENERATE

_NO_DOC_NOTICE = "⚠️ 관련 사내 문서를 찾지 못했습니다."
_RELEVANCE_THRESHOLD = 0.5


async def generate_node(state: dict, config: RunnableConfig | None = None, *, llm: LLMClient) -> dict:
    is_doc_search = state.get("route") == "doc_search"
    no_relevant_docs = (
        not state["documents"]
        or state.get("relevance_score", 1.0) < _RELEVANCE_THRESHOLD
    )

    # 내부 문서를 찾지 못하면 LLM 일반 지식 답변 대신 고지문만 반환
    if is_doc_search and no_relevant_docs:
        return {
            "answer": _NO_DOC_NOTICE,
            "citations": [],
            "hallucination_passed": True,
        }

    question = state.get("rewritten_question") or state["question"]
    history = state.get("chat_history", [])
    history_text = "\n".join(
        f"{m['role']}: {m['content']}" for m in history
    ) if history else "없음"

    context = "\n\n".join(d.chunk.text for d in state["documents"])
    prompt = RAG_GENERATE.format(
        context=context,
        question=question,
        chat_history=history_text,
    )
    citations = [SourceRef(source=d.chunk.source) for d in state["documents"]]

    text = llm.complete(prompt)

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

- [ ] **Step 5: 전체 generate 테스트 실행 — 통과 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/nodes/test_generate.py -v`
Expected: PASS (전부). `import asyncio`가 파일에서 사라졌으므로, 테스트 파일 상단의 `import asyncio`가 미사용으로 남아도 테스트는 통과한다. 단 `test_generate_node_no_queue_uses_complete`처럼 `asyncio.Queue`를 쓰는 테스트가 남아 있으면 `import asyncio`는 그대로 둔다. (테스트 파일은 수정하지 않는다.)

- [ ] **Step 6: 커밋**

```bash
git add app/graph/nodes/generate.py tests/app/graph/nodes/test_generate.py
git commit -m "refactor(generate): generate_node 큐 방출 제거, complete 전용

스트리밍은 stream_answer가 최종본만 흘리도록 이관 준비 (②-a)"
```

---

## Task 2: stream_answer가 최종 answer만 토큰 방출 (②-b)

**Files:**
- Modify: `app/graph/builder.py`
- Test: `tests/app/graph/test_builder.py`

`stream_answer`가 `graph.ainvoke()`로 그래프를 끝까지 실행해 확정된 `final["answer"]`를 받은 뒤, 토큰 청크로 쪼개 큐에 흘리고 → sources → done. 재생성이 몇 번 일어나든 최종 답변 하나만 스트림된다.

- [ ] **Step 1: 기존 스트리밍 테스트를 최종본 방출 기준으로 수정**

`tests/app/graph/test_builder.py`의 `test_stream_answer_puts_tokens_and_done_in_queue`에서, 토큰 이벤트들을 합치면 최종 answer가 되고 순서가 token…→sources→done임을 검증하도록 단언부를 교체한다. 함수 내 마지막 단언 블록(아래 old)을 new로 바꾼다.

old:
```python
    types = [e["type"] for e in events]
    assert "sources" in types
    assert types[-1] == "done"
    done_event = events[-1]
    assert done_event["session_id"] == "sess-1"

    sources_event = next(e for e in events if e["type"] == "sources")
    assert sources_event["sources"] == ["doc.md"]
```

new:
```python
    types = [e["type"] for e in events]
    assert "token" in types
    assert "sources" in types
    assert types[-1] == "done"
    done_event = events[-1]
    assert done_event["session_id"] == "sess-1"

    # 토큰 이벤트를 합치면 최종 answer가 된다 (중복 없이 1회분)
    token_events = [e for e in events if e["type"] == "token"]
    assert "".join(e["content"] for e in token_events) == "안녕하세요"

    sources_event = next(e for e in events if e["type"] == "sources")
    assert sources_event["sources"] == ["doc.md"]
    # sources는 모든 token 뒤에 온다
    assert types.index("sources") > max(i for i, t in enumerate(types) if t == "token")
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/test_builder.py::test_stream_answer_puts_tokens_and_done_in_queue -v`
Expected: FAIL — 현재 `stream_answer`는 token 이벤트를 만들지 않으므로 `assert "token" in types`에서 실패.

- [ ] **Step 3: stream_answer 구현 변경 + 청크 상수 추가**

`app/graph/builder.py` 상단(다른 모듈 상수가 없으면 import 블록 바로 아래)에 상수를 추가한다:

```python
_STREAM_CHUNK_SIZE = 3  # 의사 스트리밍 청크 크기(글자). 타이핑 효과용.
```

그리고 `stream_answer` 내 `final = await graph.ainvoke(initial, config=config)` 직후의 sources 방출 부분(아래 old)을 new로 교체한다.

old:
```python
        final = await graph.ainvoke(initial, config=config)
        await token_queue.put({
            "type": "sources",
            "sources": [s.source for s in final["citations"]],
        })
```

new:
```python
        final = await graph.ainvoke(initial, config=config)
        answer = final["answer"]
        for i in range(0, len(answer), _STREAM_CHUNK_SIZE):
            await token_queue.put({"type": "token", "content": answer[i:i + _STREAM_CHUNK_SIZE]})
        await token_queue.put({
            "type": "sources",
            "sources": [s.source for s in final["citations"]],
        })
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/test_builder.py -v`
Expected: PASS (전부). 빈 answer("")일 때 token 이벤트가 0개여도 sources/done은 정상 방출된다.

- [ ] **Step 5: 커밋**

```bash
git add app/graph/builder.py tests/app/graph/test_builder.py
git commit -m "fix(stream): 재생성 시 답변 중복 출력 제거 — 최종본만 스트림 (②-b)

stream_answer가 그래프 종료 후 확정 answer를 토큰 청크로 1회 방출.
중간 재생성 토큰이 큐에 누적되던 버그 해소."
```

---

## Task 3: RAG_GENERATE에 groundedness 제약 추가 (①-a)

**Files:**
- Modify: `app/graph/prompts.py`
- Test: `tests/app/graph/test_prompts.py` (신규)

생성 답변이 문서 청크에 근거하되 일반론·추측·수사적 부연을 덧붙이지 않도록 제약. 종합·요약은 허용하되 새 사실·수치·고유명사 날조는 금지.

- [ ] **Step 1: 프롬프트 회귀 테스트 작성 (신규 파일)**

`tests/app/graph/test_prompts.py` 생성:

```python
from app.graph.prompts import RAG_GENERATE, CHECK_HALLUCINATION


def test_rag_generate_keeps_format_fields():
    """format에 쓰이는 placeholder가 유지되어야 한다."""
    assert "{context}" in RAG_GENERATE
    assert "{question}" in RAG_GENERATE
    assert "{chat_history}" in RAG_GENERATE


def test_rag_generate_has_groundedness_constraint():
    """문서 근거 + 날조 금지 지침이 들어 있어야 한다."""
    assert "문서" in RAG_GENERATE
    assert "지어내" in RAG_GENERATE
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/test_prompts.py::test_rag_generate_has_groundedness_constraint -v`
Expected: FAIL — 현재 `RAG_GENERATE`에 "지어내" 문구 없음.

- [ ] **Step 3: RAG_GENERATE 수정**

`app/graph/prompts.py`의 `RAG_GENERATE`(아래 old)를 new로 교체.

old:
```python
RAG_GENERATE = """\
이전 대화:
{chat_history}

참고 문서:
{context}

질문: {question}
한국어로 답변하세요."""
```

new:
```python
RAG_GENERATE = """\
아래 참고 문서의 내용에만 근거해 질문에 답하세요.
- 문서에 있는 사실만 사용하고, 문서에 없는 일반 지식·추측·불필요한 수사는 덧붙이지 마세요.
- 여러 문서의 내용을 종합·요약하는 것은 괜찮지만, 문서에 없는 새로운 사실·수치·고유명사를 지어내지 마세요.
- 그 범위 안에서 자연스럽고 명확한 한국어로 답하세요.

이전 대화:
{chat_history}

참고 문서:
{context}

질문: {question}
답변:"""
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/test_prompts.py -v`
Expected: PASS.

- [ ] **Step 5: 커밋**

```bash
git add app/graph/prompts.py tests/app/graph/test_prompts.py
git commit -m "fix(prompt): RAG_GENERATE에 groundedness 제약 추가 (①-a)

문서 근거 + 일반론·수사 억제 + 날조 금지로 환각 검사 오탐의
근본 원인(생성 답변 부풀림)을 억제."
```

---

## Task 4: CHECK_HALLUCINATION 사실 주장 기준 명확화 (①-b)

**Files:**
- Modify: `app/graph/prompts.py`
- Test: `tests/app/graph/test_prompts.py` (Task 3에서 생성)

환각 검사가 문체·표현이 아니라 답변의 사실 주장이 문서에 근거하는지를 보도록 명확화. 종합·의역에 흔들리지 않게.

- [ ] **Step 1: 프롬프트 회귀 테스트 추가**

`tests/app/graph/test_prompts.py`에 함수 추가:

```python
def test_check_hallucination_keeps_format_fields():
    assert "{context}" in CHECK_HALLUCINATION
    assert "{answer}" in CHECK_HALLUCINATION


def test_check_hallucination_judges_factual_claims_not_style():
    """문체가 아니라 사실 주장 기준임이 명시되어야 한다."""
    assert "사실" in CHECK_HALLUCINATION
    assert "YES" in CHECK_HALLUCINATION and "NO" in CHECK_HALLUCINATION
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/test_prompts.py::test_check_hallucination_judges_factual_claims_not_style -v`
Expected: FAIL — 현재 `CHECK_HALLUCINATION`에 "사실" 문구 없음.

- [ ] **Step 3: CHECK_HALLUCINATION 수정**

`app/graph/prompts.py`의 `CHECK_HALLUCINATION`(아래 old)을 new로 교체.

old:
```python
CHECK_HALLUCINATION = """\
다음 답변이 제공된 문서의 내용에만 근거하는지 검증하세요.
문서에 근거한 답변이면 YES, 문서에 없는 내용이 포함되어 있으면 NO로만 답하세요.

문서:
{context}

답변: {answer}

검증 결과 (YES 또는 NO):"""
```

new:
```python
CHECK_HALLUCINATION = """\
아래 답변에 담긴 사실 주장이 제공된 문서에 근거하는지 검증하세요.
- 표현 방식·문체·요약·종합은 문제 삼지 마세요. 문서 내용을 다른 말로 풀어 쓴 것은 근거 있는 것으로 봅니다.
- 문서에 근거 없는 새로운 사실·수치·고유명사가 답변에 있으면 NO, 그렇지 않으면 YES.
- YES 또는 NO 한 단어로만 답하세요.

문서:
{context}

답변: {answer}

검증 결과 (YES 또는 NO):"""
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/test_prompts.py tests/app/graph/nodes/test_check_hallucination.py -v`
Expected: PASS (전부). `check_hallucination_node`의 로직(`"YES" in response`)은 바뀌지 않았으므로 기존 노드 테스트도 통과.

- [ ] **Step 5: 커밋**

```bash
git add app/graph/prompts.py tests/app/graph/test_prompts.py
git commit -m "fix(prompt): CHECK_HALLUCINATION을 사실 주장 기준으로 명확화 (①-b)

문체·종합·의역에 흔들리지 않고 날조만 NO 판정하도록."
```

---

## Task 5: 환각 판정 회귀 측정 스크립트 (①-c)

**Files:**
- Create: `tests/eval/eval_hallucination.py`

프롬프트 효과는 실제 LLM 판정이라 mock 단위 테스트로 검증할 수 없다. 실제 LLM으로 "근거 있는 종합 답변은 통과(YES) / 문서에 없는 날조는 차단(NO)"을 확인하는 수동 측정 스크립트를 추가한다. (`compare_reranker.py`와 같은 `tests/eval` 평가 스크립트 패턴.)

- [ ] **Step 1: 평가 스크립트 작성**

`tests/eval/eval_hallucination.py` 생성:

```python
"""환각 검사 회귀 측정 (실제 LLM).

사용법:
    .venv/bin/python -m tests.eval.eval_hallucination

.env의 LLM_PROVIDER / LLM_MODEL / API 키를 사용한다.
근거 있는 종합·의역 답변은 통과(YES), 문서에 없는 날조는 차단(NO)되어야 한다.
"""
from core.config import load_config
from core.llm.factory import create_llm
from core.models import Chunk, SearchResult
from app.graph.nodes.check_hallucination import check_hallucination_node


def _docs(*texts: str) -> list[SearchResult]:
    return [
        SearchResult(chunk=Chunk(text=t, source="doc.md", chunk_id=f"c{i}"), score=0.9)
        for i, t in enumerate(texts)
    ]


CASES = [
    {
        "name": "종합·의역 답변 (통과 기대: YES)",
        "documents": _docs(
            "배포는 스테이징 환경에서 검증을 거친 뒤 프로덕션에 반영한다.",
            "장애 발생 시 직전 버전 태그로 롤백한다.",
        ),
        "answer": (
            "배포 절차는 먼저 스테이징에서 충분히 검증한 뒤 프로덕션에 반영하며, "
            "문제가 생기면 직전 버전 태그로 신속히 롤백합니다."
        ),
        "expect_passed": True,
    },
    {
        "name": "날조 수치·고유명사 (차단 기대: NO)",
        "documents": _docs("배포는 스테이징 검증을 거친 뒤 프로덕션에 반영한다."),
        "answer": "배포는 매주 화요일 오전 3시에 자동 진행되며 최종 승인자는 CTO 김철수입니다.",
        "expect_passed": False,
    },
]


def main() -> None:
    llm = create_llm(load_config())
    ok = 0
    print("=== 환각 판정 회귀 측정 ===")
    for c in CASES:
        state = {"answer": c["answer"], "documents": c["documents"], "retry_count": 0}
        result = check_hallucination_node(state, llm=llm)
        passed = result["hallucination_passed"]
        hit = passed == c["expect_passed"]
        ok += hit
        print(f"{'✅' if hit else '❌'} {c['name']}: passed={passed} (기대={c['expect_passed']})")
    print(f"\n{ok}/{len(CASES)} 통과")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 스크립트 실행 — 측정**

Run: `.venv/bin/python -m tests.eval.eval_hallucination`
Expected: 두 케이스 모두 ✅ (`2/2 통과`). 종합 답변은 YES, 날조는 NO.
- 만약 종합 답변이 NO로 나오면(오탐 잔존) Task 3의 `RAG_GENERATE`/Task 4의 `CHECK_HALLUCINATION` 문구를 조정하고 재실행. 만약 날조가 YES로 나오면(검사 무력화) 완화가 과한 것이므로 Task 4 문구를 강화.

- [ ] **Step 3: 커밋**

```bash
git add tests/eval/eval_hallucination.py
git commit -m "test(eval): 환각 판정 회귀 측정 스크립트 추가 (①-c)

종합 답변 통과 / 날조 차단을 실제 LLM으로 검증하는 수동 측정 도구."
```

---

## Task 6: 통합 검증

**Files:** (없음 — 검증만)

- [ ] **Step 1: 전체 단위 테스트 실행**

Run: `.venv/bin/python -m pytest -q`
Expected: 전부 PASS (기존 + 신규 test_prompts.py, 수정된 test_generate.py/test_builder.py). 실패 시 해당 Task로 돌아가 수정.

- [ ] **Step 2: 수동 검증 (LangSmith) — 선택, 인프라 필요**

Postgres·OpenFGA·OpenAI 키가 갖춰진 환경에서:
1. `.venv/bin/python -m uvicorn app.api.chat:app --host 127.0.0.1 --port 8000` 기동
2. alice(`alice123`) 로그인 후 프론트(`/chat/stream`)에서 "배포는 어떤 절차로 진행해?" 질문
3. 확인: 답변이 **한 벌만** 표시(중복 없음). LangSmith project `company-rag` 트레이스에서 `generate` 재실행 횟수가 0~1회로 감소(이전엔 retry_count 3까지).

- [ ] **Step 3: 최종 커밋 (검증 메모, 변경 없으면 생략)**

검증만 했고 코드 변경이 없으면 커밋하지 않는다.

---

## Self-Review

**1. Spec coverage**
- spec §3.1 generate groundedness → Task 3 ✅
- spec §3.2 check 사실주장 기준 → Task 4 ✅
- spec §3.3 측정 → Task 5 ✅
- spec §4 generate 큐 제거 → Task 1 ✅
- spec §4 stream_answer 최종본 → Task 2 ✅
- spec §5 검증(단위·수동·회귀) → Task 1~6 각 테스트 + Task 6 ✅
- spec §2 비목표(LLM 계측 ③, 재생성 루프 제거) → 계획에 포함하지 않음 ✅

**2. Placeholder scan:** "TBD/TODO" 없음. 모든 코드 단계에 완전한 before/after 코드와 실행 명령·기대값 포함.

**3. Type consistency:** `generate_node(state, config, *, llm)` 시그니처 유지(Task 1), `stream_answer`의 `token_queue.put({"type": "token"|"sources"|"done"|"error"})` 이벤트 형식 일관(Task 2), `check_hallucination_node(state, *, llm)` → `{"hallucination_passed": bool}` 호출 형식 Task 5와 일치, `create_llm(load_config())` → `LLMClient` 사용 일관.
