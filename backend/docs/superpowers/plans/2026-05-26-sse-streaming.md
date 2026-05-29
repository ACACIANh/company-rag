# SSE 스트리밍 응답 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** LLM 토큰 단위 SSE 스트리밍 지원 — `POST /chat/stream` 엔드포인트 추가, 프론트 실시간 렌더링 연동

**Architecture:** `asyncio.Queue`를 LangGraph config의 `configurable.token_queue`로 전달. `generate_node`가 `llm.stream()`으로 토큰을 큐에 put. FastAPI `StreamingResponse`가 큐를 읽어 SSE 형식으로 yield. `queue=None`이면 기존 `llm.complete()` 경로 유지.

**Tech Stack:** Python asyncio, FastAPI StreamingResponse, anthropic AsyncAnthropic, openai AsyncOpenAI, TypeScript fetch+ReadableStream

---

## 파일 변경 목록

| 파일 | 작업 |
|---|---|
| `shared/llm/base.py` | `stream()` 추상 메서드 추가 |
| `shared/llm/anthropic_client.py` | `AsyncAnthropic` + `stream()` 구현 |
| `shared/llm/openai_client.py` | `AsyncOpenAI` + `stream()` 구현 |
| `app/graph/nodes/generate.py` | `async def`로 전환, `token_queue` 분기 추가 |
| `app/graph/builder.py` | `stream_answer()` 함수 추가 |
| `app/api/chat.py` | `POST /chat/stream` 엔드포인트 추가 |
| `web/src/types.ts` | `SSEEvent` 타입 추가 |
| `web/src/api/client.ts` | `streamChat()` 함수 추가 |
| `web/src/chat/ChatPage.tsx` | `send()` 스트리밍으로 교체 |
| `tests/shared/test_llm.py` | `stream()` 단위 테스트 추가 |
| `tests/app/graph/nodes/test_generate.py` | async 테스트로 업데이트 + 스트리밍 케이스 추가 |
| `tests/app/api/test_chat_stream.py` | 신규: SSE 엔드포인트 통합 테스트 |
| `web/src/api/client.test.ts` | `streamChat()` 테스트 추가 |

---

## Task 1: LLMClient.stream() ABC + AnthropicClient 구현

**Files:**
- Modify: `shared/llm/base.py`
- Modify: `shared/llm/anthropic_client.py`
- Modify: `tests/shared/test_llm.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/shared/test_llm.py` 맨 아래에 추가:

```python
import asyncio


def test_llm_abstract_requires_stream():
    """stream()을 구현하지 않은 서브클래스는 인스턴스화 불가."""
    class NoStream(LLMClient):
        def complete(self, prompt: str) -> str:
            return ""
    with pytest.raises(TypeError):
        NoStream()


@pytest.mark.asyncio
async def test_anthropic_client_stream(mocker):
    """stream()이 토큰 시퀀스를 yield한다."""
    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_stream_ctx)
    mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)

    async def _text_stream():
        for t in ["안", "녕", "하", "세요"]:
            yield t

    mock_stream_ctx.text_stream = _text_stream()
    mocker.patch("shared.llm.anthropic_client.anthropic.AsyncAnthropic")

    client = AnthropicClient(model="claude-3-haiku-20240307", api_key="test-key")
    client._async_client.messages.stream.return_value = mock_stream_ctx

    tokens = []
    async for token in client.stream("테스트"):
        tokens.append(token)

    assert tokens == ["안", "녕", "하", "세요"]
```

- [ ] **Step 2: 테스트 실행 — FAIL 확인**

```bash
pytest tests/shared/test_llm.py::test_llm_abstract_requires_stream \
       tests/shared/test_llm.py::test_anthropic_client_stream -v
```

Expected: `FAILED` — `TypeError: Can't instantiate abstract class` 미발생 (stream 미정의) + `AttributeError` (AsyncAnthropic 없음)

- [ ] **Step 3: `shared/llm/base.py` 수정**

```python
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class LLMClient(ABC):
    @abstractmethod
    def complete(self, prompt: str) -> str: ...

    @abstractmethod
    def stream(self, prompt: str) -> AsyncIterator[str]: ...
```

- [ ] **Step 4: `shared/llm/anthropic_client.py` 수정**

```python
from collections.abc import AsyncIterator

import anthropic

from shared.llm.base import LLMClient


class AnthropicClient(LLMClient):
    def __init__(self, model: str, api_key: str) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self._async_client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    def complete(self, prompt: str) -> str:
        message = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        async with self._async_client.messages.stream(
            model=self._model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        ) as s:
            async for text in s.text_stream:
                yield text
```

- [ ] **Step 5: 테스트 실행 — PASS 확인**

```bash
pytest tests/shared/test_llm.py -v
```

Expected: 모든 테스트 PASS (기존 테스트 포함)

- [ ] **Step 6: 커밋**

```bash
git add shared/llm/base.py shared/llm/anthropic_client.py tests/shared/test_llm.py
git commit -m "feat(llm): LLMClient.stream() ABC 추가 + AnthropicClient 구현"
```

---

## Task 2: OpenAIClient.stream() 구현

**Files:**
- Modify: `shared/llm/openai_client.py`
- Modify: `tests/shared/test_llm.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/shared/test_llm.py`에 추가:

```python
@pytest.mark.asyncio
async def test_openai_client_stream(mocker):
    """OpenAIClient.stream()이 delta.content 토큰을 yield한다."""
    def _make_chunk(text):
        chunk = MagicMock()
        chunk.choices[0].delta.content = text
        return chunk

    mock_aiter = MagicMock()
    mock_aiter.__aiter__ = MagicMock(return_value=mock_aiter)
    mock_aiter.__anext__ = AsyncMock(side_effect=[
        _make_chunk("Hello"),
        _make_chunk(" world"),
        StopAsyncIteration,
    ])

    mocker.patch("shared.llm.openai_client.OpenAI")
    mocker.patch("shared.llm.openai_client.AsyncOpenAI")

    client = OpenAIClient(model="gpt-4o-mini", api_key="test-key")
    client._async_client.chat.completions.create.return_value = mock_aiter

    tokens = []
    async for token in client.stream("테스트"):
        tokens.append(token)

    assert tokens == ["Hello", " world"]
```

- [ ] **Step 2: 테스트 실행 — FAIL 확인**

```bash
pytest tests/shared/test_llm.py::test_openai_client_stream -v
```

Expected: `FAILED` — `AttributeError: _async_client` 없음

- [ ] **Step 3: `shared/llm/openai_client.py` 수정**

```python
from collections.abc import AsyncIterator

from openai import AsyncOpenAI, OpenAI

from shared.llm.base import LLMClient


class OpenAIClient(LLMClient):
    def __init__(self, model: str, api_key: str) -> None:
        self._client = OpenAI(api_key=api_key)
        self._async_client = AsyncOpenAI(api_key=api_key)
        self._model = model

    def complete(self, prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        response = await self._async_client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
        )
        async for chunk in response:
            content = chunk.choices[0].delta.content
            if content:
                yield content
```

- [ ] **Step 4: 테스트 실행 — PASS 확인**

```bash
pytest tests/shared/test_llm.py -v
```

Expected: 모든 테스트 PASS

- [ ] **Step 5: 커밋**

```bash
git add shared/llm/openai_client.py tests/shared/test_llm.py
git commit -m "feat(llm): OpenAIClient.stream() 구현"
```

---

## Task 3: generate_node async 전환 + token_queue 분기

**Files:**
- Modify: `app/graph/nodes/generate.py`
- Modify: `tests/app/graph/nodes/test_generate.py`

- [ ] **Step 1: 기존 테스트를 async로 업데이트**

`tests/app/graph/nodes/test_generate.py` 전체를 아래로 교체:

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.models import Chunk, SearchResult, SourceRef
from app.graph.nodes.generate import generate_node


def _make_result(text: str, source: str, sensitivity: str = "public",
                 team_id: str = "", doc_id: str = "") -> SearchResult:
    return SearchResult(
        chunk=Chunk(
            text=text,
            source=source,
            chunk_id="test_id",
            metadata={"sensitivity": sensitivity, "team_id": team_id, "document_id": doc_id},
        ),
        score=0.9,
    )


@pytest.mark.asyncio
async def test_generate_node_returns_source_refs():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "테스트 답변"

    state = {
        "question": "질문",
        "documents": [_make_result("내용", "doc.md", sensitivity="internal",
                                   team_id="team:dev", doc_id="doc:1")],
    }
    result = await generate_node(state, llm=mock_llm)

    assert result["answer"] == "테스트 답변"
    assert len(result["citations"]) == 1
    ref = result["citations"][0]
    assert isinstance(ref, SourceRef)
    assert ref.source == "doc.md"
    assert ref.sensitivity == "internal"
    assert ref.team_id == "team:dev"
    assert ref.document_id == "doc:1"


@pytest.mark.asyncio
async def test_generate_node_defaults_to_public_when_no_metadata():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "답변"

    state = {
        "question": "질문",
        "documents": [SearchResult(
            chunk=Chunk(text="내용", source="doc.md", chunk_id="id"), score=0.9
        )],
    }
    result = await generate_node(state, llm=mock_llm)
    ref = result["citations"][0]
    assert isinstance(ref, SourceRef)
    assert ref.sensitivity == "public"
    assert ref.team_id == ""
    assert ref.document_id == ""


@pytest.mark.asyncio
async def test_generate_node_includes_context_in_prompt():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "답변"

    state = {
        "question": "질문",
        "documents": [_make_result("중요한 내용", "doc.md")],
    }
    await generate_node(state, llm=mock_llm)

    called_prompt = mock_llm.complete.call_args[0][0]
    assert "중요한 내용" in called_prompt
    assert "질문" in called_prompt


@pytest.mark.asyncio
async def test_generate_node_uses_rewritten_question_in_prompt():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "답변"

    state = {
        "question": "원본 질문",
        "rewritten_question": "재작성된 질문",
        "documents": [_make_result("문서 내용", "doc.md")],
    }
    await generate_node(state, llm=mock_llm)

    prompt = mock_llm.complete.call_args[0][0]
    assert "재작성된 질문" in prompt
    assert "원본 질문" not in prompt


@pytest.mark.asyncio
async def test_generate_node_falls_back_to_question_when_rewritten_empty():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "답변"

    state = {
        "question": "원본 질문",
        "rewritten_question": "",
        "documents": [_make_result("내용", "doc.md")],
    }
    await generate_node(state, llm=mock_llm)

    prompt = mock_llm.complete.call_args[0][0]
    assert "원본 질문" in prompt


@pytest.mark.asyncio
async def test_generate_node_includes_chat_history_in_prompt():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "답변"

    history = [{"role": "user", "content": "이전 대화 내용"}]
    state = {
        "question": "질문",
        "rewritten_question": "재작성",
        "documents": [_make_result("문서", "doc.md")],
        "chat_history": history,
    }
    await generate_node(state, llm=mock_llm)

    prompt = mock_llm.complete.call_args[0][0]
    assert "이전 대화 내용" in prompt


_NOTICE_PREFIX = "⚠️ 관련 사내 문서를 찾지 못했습니다."


@pytest.mark.asyncio
async def test_generate_node_prepends_notice_when_no_documents():
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
    result = await generate_node(state, llm=mock_llm)

    assert result["answer"].startswith(_NOTICE_PREFIX)
    assert "일반 답변" in result["answer"]
    assert result["citations"] == []


@pytest.mark.asyncio
async def test_generate_node_prepends_notice_when_low_relevance():
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
    result = await generate_node(state, llm=mock_llm)

    assert result["answer"].startswith(_NOTICE_PREFIX)
    assert "일반 답변" in result["answer"]
    assert result["citations"] == []


@pytest.mark.asyncio
async def test_generate_node_no_notice_when_relevant_docs_exist():
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
    result = await generate_node(state, llm=mock_llm)

    assert not result["answer"].startswith(_NOTICE_PREFIX)
    assert result["answer"] == "문서 기반 답변"
    assert len(result["citations"]) == 1


@pytest.mark.asyncio
async def test_generate_node_no_notice_for_web_search_route():
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
    result = await generate_node(state, llm=mock_llm)

    assert not result["answer"].startswith(_NOTICE_PREFIX)
    assert result["answer"] == "웹 검색 답변"


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


@pytest.mark.asyncio
async def test_generate_node_no_queue_uses_complete():
    """token_queue 없을 때 llm.complete() 폴백."""
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "complete 답변"

    state = {
        "question": "질문",
        "rewritten_question": "질문",
        "documents": [_make_result("내용", "doc.md")],
        "relevance_score": 0.9,
        "route": "doc_search",
        "chat_history": [],
    }

    result = await generate_node(state, llm=mock_llm)

    mock_llm.complete.assert_called_once()
    assert result["answer"] == "complete 답변"


@pytest.mark.asyncio
async def test_generate_node_streams_notice_prefix_when_no_docs():
    """no-doc 경로에서 _NO_DOC_NOTICE도 토큰으로 스트리밍된다."""

    async def _fake_stream(prompt):
        yield "일반 답변"

    mock_llm = MagicMock()
    mock_llm.stream = _fake_stream

    queue: asyncio.Queue = asyncio.Queue()
    state = {
        "question": "질문",
        "rewritten_question": "질문",
        "documents": [],
        "relevance_score": 0.0,
        "route": "doc_search",
        "chat_history": [],
    }
    config = {"configurable": {"token_queue": queue}}

    result = await generate_node(state, config=config, llm=mock_llm)

    tokens = [q["content"] for q in list(queue._queue)]
    assert tokens[0].startswith("⚠️")   # notice prefix가 첫 토큰
    assert "일반 답변" in "".join(tokens)
    assert result["answer"].startswith("⚠️")
```

- [ ] **Step 2: 테스트 실행 — 기존 테스트 실패 확인 (async 미지원)**

```bash
pytest tests/app/graph/nodes/test_generate.py -v
```

Expected: 모든 테스트 FAIL (coroutine was never awaited 또는 sync call 에러)

- [ ] **Step 3: `app/graph/nodes/generate.py` 수정**

```python
import asyncio

from langchain_core.runnables import RunnableConfig

from shared.llm.base import LLMClient
from shared.models import SourceRef
from shared.observability.cost_tracker import get_tracker
from app.graph.prompts import RAG_GENERATE, RAG_GENERATE_NO_DOCS

_NO_DOC_NOTICE = (
    "⚠️ 관련 사내 문서를 찾지 못했습니다.\n"
    "일반 지식을 바탕으로 답변드립니다.\n\n---\n\n"
)
_RELEVANCE_THRESHOLD = 0.5


async def generate_node(state: dict, config: RunnableConfig | None = None, *, llm: LLMClient) -> dict:
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

    queue: asyncio.Queue | None = (
        (config or {}).get("configurable", {}).get("token_queue")
    )

    if is_doc_search and no_relevant_docs:
        prompt = RAG_GENERATE_NO_DOCS.format(
            chat_history=history_text,
            question=question,
        )
        prefix = _NO_DOC_NOTICE
        citations = []
    else:
        context = "\n\n".join(d.chunk.text for d in state["documents"])
        prompt = RAG_GENERATE.format(
            context=context,
            question=question,
            chat_history=history_text,
        )
        prefix = ""
        citations = [
            SourceRef(
                source=d.chunk.source,
                document_id=d.chunk.metadata.get("document_id", ""),
                sensitivity=d.chunk.metadata.get("sensitivity", "public"),
                team_id=d.chunk.metadata.get("team_id", ""),
            )
            for d in state["documents"]
        ]

    if queue is not None:
        tokens = []
        if prefix:
            await queue.put({"type": "token", "content": prefix})
            tokens.append(prefix)
        async for token in llm.stream(prompt):
            await queue.put({"type": "token", "content": token})
            tokens.append(token)
        text = "".join(tokens)
    else:
        text = prefix + llm.complete(prompt)

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

- [ ] **Step 4: 테스트 실행 — PASS 확인**

```bash
pytest tests/app/graph/nodes/test_generate.py -v
```

Expected: 모든 테스트 PASS

- [ ] **Step 5: 전체 테스트 suite 회귀 확인**

```bash
pytest tests/app/graph/ -v
```

Expected: 모든 테스트 PASS

- [ ] **Step 6: 커밋**

```bash
git add app/graph/nodes/generate.py tests/app/graph/nodes/test_generate.py
git commit -m "feat(generate): async 전환 + token_queue 스트리밍 분기 추가"
```

---

## Task 4: stream_answer() in builder.py

**Files:**
- Modify: `app/graph/builder.py`
- Modify: `tests/app/graph/test_builder.py` (확인 후 신규 테스트 추가)

- [ ] **Step 1: 기존 builder 테스트 확인**

```bash
pytest tests/app/graph/test_builder.py -v
```

Expected: PASS (기존 테스트 영향 없는지 확인)

- [ ] **Step 2: 실패 테스트 작성**

`tests/app/graph/test_builder.py`에 추가:

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_stream_answer_puts_tokens_and_done_in_queue():
    """stream_answer가 토큰→sources→done 순서로 큐에 넣는다."""
    from app.graph.builder import stream_answer
    from shared.models import SourceRef

    mock_final = {
        "answer": "안녕하세요",
        "citations": [SourceRef(source="doc.md")],
    }
    mock_graph = MagicMock()
    mock_graph.get_state.return_value = MagicMock(values={})
    mock_graph.ainvoke = AsyncMock(return_value=mock_final)

    mock_store = AsyncMock()
    queue: asyncio.Queue = asyncio.Queue()

    await stream_answer(
        graph=mock_graph,
        question="질문",
        config={"configurable": {"thread_id": "t1"}},
        user_id="alice",
        allowed_doc_ids=[],
        token_queue=queue,
        session_store=mock_store,
        session_id="sess-1",
        is_new_session=True,
    )

    events = []
    while not queue.empty():
        events.append(queue.get_nowait())

    types = [e["type"] for e in events]
    assert "sources" in types
    assert types[-1] == "done"
    done_event = events[-1]
    assert done_event["session_id"] == "sess-1"

    sources_event = next(e for e in events if e["type"] == "sources")
    assert sources_event["sources"] == ["doc.md"]


@pytest.mark.asyncio
async def test_stream_answer_puts_error_then_done_on_exception():
    """graph.ainvoke 예외 시 error→done 순서로 큐에 넣는다."""
    from app.graph.builder import stream_answer

    mock_graph = MagicMock()
    mock_graph.get_state.return_value = MagicMock(values={})
    mock_graph.ainvoke = AsyncMock(side_effect=RuntimeError("LLM 오류"))

    mock_store = AsyncMock()
    queue: asyncio.Queue = asyncio.Queue()

    await stream_answer(
        graph=mock_graph,
        question="질문",
        config={"configurable": {"thread_id": "t1"}},
        user_id="alice",
        allowed_doc_ids=[],
        token_queue=queue,
        session_store=mock_store,
        session_id="sess-1",
        is_new_session=False,
    )

    events = []
    while not queue.empty():
        events.append(queue.get_nowait())

    assert events[0]["type"] == "error"
    assert "LLM 오류" in events[0]["message"]
    assert events[1]["type"] == "done"


@pytest.mark.asyncio
async def test_stream_answer_saves_session():
    """완료 후 session_store에 user/assistant 메시지를 기록한다."""
    from app.graph.builder import stream_answer
    from shared.models import SourceRef

    mock_final = {"answer": "답변", "citations": []}
    mock_graph = MagicMock()
    mock_graph.get_state.return_value = MagicMock(values={})
    mock_graph.ainvoke = AsyncMock(return_value=mock_final)

    mock_store = AsyncMock()
    queue: asyncio.Queue = asyncio.Queue()

    await stream_answer(
        graph=mock_graph,
        question="안녕",
        config={"configurable": {"thread_id": "t1"}},
        user_id="alice",
        allowed_doc_ids=[],
        token_queue=queue,
        session_store=mock_store,
        session_id="sess-2",
        is_new_session=True,
    )

    mock_store.create_session.assert_called_once_with("sess-2", "alice", "안녕")
    assert mock_store.add_message.call_count == 2
```

- [ ] **Step 3: 테스트 실행 — FAIL 확인**

```bash
pytest tests/app/graph/test_builder.py -k "stream_answer" -v
```

Expected: `FAILED` — `ImportError: cannot import name 'stream_answer'`

- [ ] **Step 4: `app/graph/builder.py`에 `stream_answer()` 추가**

기존 코드 뒤에 추가 (import에 `asyncio`, `logging` 추가):

```python
import asyncio
import logging
import uuid
from functools import partial

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from shared.llm.base import LLMClient
from shared.models import Answer
from shared.reranker.base import Reranker
from shared.retriever.base import Retriever
from shared.fga.client import FGAClient
# ... (기존 import 유지) ...
```

파일 맨 아래에 추가:

```python
async def stream_answer(
    graph: CompiledStateGraph,
    question: str,
    config: dict,
    user_id: str,
    allowed_doc_ids: list[str],
    token_queue: asyncio.Queue,
    session_store,
    session_id: str,
    is_new_session: bool,
) -> None:
    config = _ensure_thread_id(config)
    config["configurable"]["token_queue"] = token_queue
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
        "user_id": user_id,
        "allowed_doc_ids": allowed_doc_ids or [],
        "user_teams": [],
        "personal_doc_ids": [],
    }

    try:
        final = await graph.ainvoke(initial, config=config)
        await token_queue.put({
            "type": "sources",
            "sources": [s.source for s in final["citations"]],
        })
        await token_queue.put({"type": "done", "session_id": session_id})
        try:
            if is_new_session:
                await session_store.create_session(session_id, user_id, question[:20])
            await session_store.add_message(session_id, "user", question, [])
            await session_store.add_message(session_id, "assistant", final["answer"], final["citations"])
        except Exception:
            logging.exception("session store write failed for session_id=%s", session_id)
    except Exception as exc:
        await token_queue.put({"type": "error", "message": str(exc)})
        await token_queue.put({"type": "done", "session_id": session_id})
```

- [ ] **Step 5: 테스트 실행 — PASS 확인**

```bash
pytest tests/app/graph/test_builder.py -v
```

Expected: 모든 테스트 PASS

- [ ] **Step 6: 커밋**

```bash
git add app/graph/builder.py tests/app/graph/test_builder.py
git commit -m "feat(builder): stream_answer() 추가 — token_queue 기반 스트리밍 실행"
```

---

## Task 5: POST /chat/stream 엔드포인트

**Files:**
- Modify: `app/api/chat.py`
- Create: `tests/app/api/test_chat_stream.py`

- [ ] **Step 1: 테스트 파일 생성**

`tests/app/api/test_chat_stream.py`:

```python
"""POST /chat/stream SSE 엔드포인트 테스트."""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def _get_token(client: TestClient) -> str:
    res = client.post("/auth/token", json={"username": "alice", "password": "alice123"})
    return res.json()["access_token"]


async def _fake_stream_answer(**kwargs):
    queue: asyncio.Queue = kwargs["token_queue"]
    await queue.put({"type": "token", "content": "안녕"})
    await queue.put({"type": "token", "content": "하세요"})
    await queue.put({"type": "sources", "sources": ["doc.md"]})
    await queue.put({"type": "done", "session_id": kwargs["session_id"]})


def test_chat_stream_returns_sse_events():
    from app.api.chat import app

    with patch("app.api.chat.stream_answer", side_effect=_fake_stream_answer):
        client = TestClient(app)
        token = _get_token(client)
        with client.stream(
            "POST",
            "/chat/stream",
            json={"question": "테스트"},
            headers={"Authorization": f"Bearer {token}"},
        ) as resp:
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers["content-type"]

            lines = resp.text.strip().split("\n\n")
            events = [json.loads(line.removeprefix("data: ")) for line in lines if line.startswith("data:")]

    types = [e["type"] for e in events]
    assert "token" in types
    assert "sources" in types
    assert types[-1] == "done"


def test_chat_stream_token_content():
    from app.api.chat import app

    with patch("app.api.chat.stream_answer", side_effect=_fake_stream_answer):
        client = TestClient(app)
        token = _get_token(client)
        with client.stream(
            "POST",
            "/chat/stream",
            json={"question": "테스트"},
            headers={"Authorization": f"Bearer {token}"},
        ) as resp:
            lines = resp.text.strip().split("\n\n")
            events = [json.loads(line.removeprefix("data: ")) for line in lines if line.startswith("data:")]

    token_events = [e for e in events if e["type"] == "token"]
    assert [e["content"] for e in token_events] == ["안녕", "하세요"]


def test_chat_stream_returns_401_without_token():
    from app.api.chat import app
    client = TestClient(app)
    resp = client.post("/chat/stream", json={"question": "테스트"})
    assert resp.status_code == 401


def test_chat_stream_returns_403_for_foreign_session():
    from app.api.chat import app

    mock_session = AsyncMock()
    mock_session.list_sessions = AsyncMock(return_value=[])
    app.state.session_store = mock_session

    client = TestClient(app)
    token = _get_token(client)
    resp = client.post(
        "/chat/stream",
        json={"question": "테스트", "session_id": "other-session"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
```

- [ ] **Step 2: 테스트 실행 — FAIL 확인**

```bash
pytest tests/app/api/test_chat_stream.py -v
```

Expected: `FAILED` — `404 Not Found` (`/chat/stream` 없음)

- [ ] **Step 3: `app/api/chat.py`에 엔드포인트 추가**

기존 import 목록에 추가:

```python
import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager

import asyncpg
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pgvector.asyncpg import register_vector
# ... 기존 import ...
from app.graph.builder import answer_question, build_graph, stream_answer
```

`chat()` 엔드포인트 뒤에 추가:

```python
@app.post("/chat/stream")
async def chat_stream(
    req: ChatRequest,
    request: Request,
    current_user: AuthUser = Depends(get_current_user),
    _: None = Depends(check_rate_limit),
) -> StreamingResponse:
    session_id = req.session_id or str(uuid.uuid4())
    is_new_session = req.session_id is None
    store = request.app.state.session_store

    if not is_new_session:
        owned = {s.thread_id for s in await store.list_sessions(current_user["user_id"])}
        if session_id not in owned:
            raise HTTPException(status_code=403, detail="Session not found")

    thread_id = f"{current_user['user_id']}:{session_id}"
    config = {"configurable": {"thread_id": thread_id}}

    async def event_generator():
        token_queue: asyncio.Queue = asyncio.Queue()
        task = asyncio.create_task(
            stream_answer(
                graph=request.app.state.graph,
                question=req.question,
                config=config,
                user_id=current_user["user_id"],
                allowed_doc_ids=current_user["allowed_doc_ids"],
                token_queue=token_queue,
                session_store=store,
                session_id=session_id,
                is_new_session=is_new_session,
            )
        )
        try:
            while True:
                event = await token_queue.get()
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event.get("type") == "done":
                    break
        finally:
            task.cancel()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

- [ ] **Step 4: 테스트 실행 — PASS 확인**

```bash
pytest tests/app/api/test_chat_stream.py -v
```

Expected: 모든 테스트 PASS

- [ ] **Step 5: 기존 chat 테스트 회귀 확인**

```bash
pytest tests/app/api/ -v
```

Expected: 모든 테스트 PASS

- [ ] **Step 6: 커밋**

```bash
git add app/api/chat.py tests/app/api/test_chat_stream.py
git commit -m "feat(api): POST /chat/stream SSE 스트리밍 엔드포인트 추가"
```

---

## Task 6: Frontend — SSEEvent 타입 + streamChat()

**Files:**
- Modify: `web/src/types.ts`
- Modify: `web/src/api/client.ts`
- Modify: `web/src/api/client.test.ts`

- [ ] **Step 1: 실패 테스트 작성**

`web/src/api/client.test.ts` 상단 import 교체:

```typescript
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { ApiError, SSEEvent } from "../types";
import { apiFetch, setOnUnauthorized, streamChat } from "./client";
```

이후 파일 맨 아래에 추가:

```typescript
describe("streamChat", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function makeStreamResponse(lines: string[]): Response {
    const body = lines.join("\n\n") + "\n\n";
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(body));
        controller.close();
      },
    });
    return new Response(stream, {
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
    });
  }

  test("yields token events from SSE stream", async () => {
    localStorage.setItem("token", "test-token");
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      makeStreamResponse([
        'data: {"type":"token","content":"안녕"}',
        'data: {"type":"token","content":"하세요"}',
        'data: {"type":"sources","sources":["doc.md"]}',
        'data: {"type":"done","session_id":"abc"}',
      ])
    );

    const events: SSEEvent[] = [];
    for await (const event of streamChat("테스트", null)) {
      events.push(event);
    }

    expect(events).toHaveLength(4);
    expect(events[0]).toEqual({ type: "token", content: "안녕" });
    expect(events[3]).toEqual({ type: "done", session_id: "abc" });
  });

  test("throws ApiError on 401", async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      new Response(JSON.stringify({ detail: "Unauthorized" }), { status: 401 })
    );

    await expect(async () => {
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      for await (const _ of streamChat("질문", null)) { /* noop */ }
    }).rejects.toBeInstanceOf(ApiError);
  });
});
```

- [ ] **Step 2: 테스트 실행 — FAIL 확인**

```bash
cd web && npm test -- --run src/api/client.test.ts
```

Expected: `FAILED` — `streamChat is not exported`

- [ ] **Step 3: `web/src/types.ts`에 SSEEvent 추가**

기존 타입 뒤에 추가:

```typescript
export type SSEEvent =
  | { type: "token";   content: string }
  | { type: "sources"; sources: string[] }
  | { type: "done";    session_id: string }
  | { type: "error";   message: string };
```

- [ ] **Step 4: `web/src/api/client.ts`에 streamChat() 추가**

import 추가:

```typescript
import { ApiError, Session, SessionMessage, SSEEvent } from "../types";
```

파일 맨 아래에 추가:

```typescript
export async function* streamChat(
  question: string,
  sessionId: string | null
): AsyncGenerator<SSEEvent> {
  const token = localStorage.getItem("token");
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const response = await fetch(`${BASE_URL}/chat/stream`, {
    method: "POST",
    headers,
    body: JSON.stringify({ question, session_id: sessionId }),
  });

  if (response.status === 401) {
    if (onUnauthorized) onUnauthorized();
    throw new ApiError(401, await safeMessage(response));
  }
  if (!response.ok) {
    throw new ApiError(response.status, await safeMessage(response));
  }

  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      const line = part.replace(/^data: /, "").trim();
      if (line) yield JSON.parse(line) as SSEEvent;
    }
  }
}
```

- [ ] **Step 5: 테스트 실행 — PASS 확인**

```bash
cd web && npm test -- --run src/api/client.test.ts
```

Expected: 모든 테스트 PASS

- [ ] **Step 6: 커밋**

```bash
git add web/src/types.ts web/src/api/client.ts web/src/api/client.test.ts
git commit -m "feat(frontend): SSEEvent 타입 + streamChat() 추가"
```

---

## Task 7: ChatPage.tsx — 스트리밍 send() 교체

**Files:**
- Modify: `web/src/chat/ChatPage.tsx`

- [ ] **Step 1: `web/src/chat/ChatPage.tsx`의 `send()` 함수 교체**

기존 import에 `streamChat` 추가:

```typescript
import { apiFetch, getSessions, getSessionMessages, deleteSession, streamChat } from "../api/client";
import type { ChatMessage, Session, SSEEvent } from "../types";
```

`send` 함수를 아래로 교체:

```typescript
const send = async (question: string) => {
  const isNewSession = sessionId === null;
  setError(null);
  setPending(true);
  setMessages((prev) => [
    ...prev,
    { role: "user", content: question },
    { role: "assistant", content: "", sources: [] },
  ]);

  try {
    for await (const event of streamChat(question, sessionId)) {
      if (event.type === "token") {
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          next[next.length - 1] = { ...last, content: last.content + event.content };
          return next;
        });
      } else if (event.type === "sources") {
        setMessages((prev) => {
          const next = [...prev];
          next[next.length - 1] = { ...next[next.length - 1], sources: event.sources };
          return next;
        });
      } else if (event.type === "done") {
        setSessionId(event.session_id);
        if (isNewSession) {
          getSessions().then(setSessions).catch(() => {});
        }
      } else if (event.type === "error") {
        setError(event.message);
      }
    }
  } catch (err) {
    if (err instanceof ApiError) {
      if (err.status === 429 && err.retryAfter !== undefined) {
        setError(`요청이 많습니다. ${err.retryAfter}초 후 다시 시도하세요.`);
      } else if (err.status !== 401) {
        setError(err.message || "요청 처리 중 오류가 발생했습니다.");
      }
    } else {
      setError("네트워크 오류가 발생했습니다.");
    }
  } finally {
    setPending(false);
  }
};
```

- [ ] **Step 2: 타입 에러 확인**

```bash
cd web && npx tsc --noEmit
```

Expected: 에러 없음

- [ ] **Step 3: 기존 ChatPage 테스트 실행**

```bash
cd web && npm test -- --run src/chat/ChatPage.test.tsx
```

Expected: PASS (기존 테스트 회귀 없음)
> Note: 기존 테스트가 `apiFetch("/chat", ...)` mock을 사용한다면 `streamChat` mock으로 업데이트 필요. 실패 시 해당 테스트의 mock을 `streamChat`으로 교체.

- [ ] **Step 4: 전체 프론트엔드 테스트**

```bash
cd web && npm test -- --run
```

Expected: 모든 테스트 PASS

- [ ] **Step 5: 커밋**

```bash
git add web/src/chat/ChatPage.tsx
git commit -m "feat(ui): ChatPage send() 스트리밍으로 교체 — 토큰 실시간 렌더링"
```

---

## Task 8: 회귀 테스트 & eval

- [ ] **Step 1: 전체 백엔드 테스트 실행**

```bash
pytest -v --tb=short
```

Expected: 모든 테스트 PASS. 실패 시 오류 메시지 보고.

- [ ] **Step 2: eval 회귀 점수 확인**

```bash
python tests/eval/runner.py
```

Expected: 기존 점수 대비 하락 없음. 하락 시 원인 명시.

- [ ] **Step 3: 최종 커밋 (변경사항 없을 경우 생략)**

```bash
git log --oneline -8
```

---

## 완료 기준 (DoD)

- [ ] `POST /chat/stream` → SSE 이벤트 순서: `token` × N → `sources` → `done`
- [ ] `POST /chat` 기존 엔드포인트 동작 그대로
- [ ] `token_queue=None`일 때 `llm.complete()` 폴백 정상 동작
- [ ] 프론트엔드에서 토큰 실시간 렌더링 (빈 assistant 메시지에 append)
- [ ] 모든 단위/통합 테스트 PASS
- [ ] eval 점수 하락 없음
