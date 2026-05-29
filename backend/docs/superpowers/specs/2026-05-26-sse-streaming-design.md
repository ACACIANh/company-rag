# SSE 스트리밍 응답 설계

**날짜**: 2026-05-26  
**백로그 항목**: B-6 — `POST /chat` SSE 스트리밍, 프론트 연동 포함  
**범위**: 토큰 단위 스트리밍 (doc_search / web_search 경로). tool_call (HITL) 경로 제외.

---

## 1. 목표

LLM이 토큰을 생성하는 즉시 클라이언트에 전달해 체감 응답 속도(TTFT)를 개선한다.  
기존 `POST /chat` 엔드포인트는 변경하지 않는다.

---

## 2. 아키텍처 & 데이터 흐름

```
[프론트] POST /chat/stream
         body: {question, session_id}
         header: Authorization: Bearer <jwt>
    │
    ▼
[FastAPI] StreamingResponse(media_type="text/event-stream")
    │  asyncio.Queue 생성 (token_queue)
    │  asyncio.create_task(stream_answer(graph, ..., token_queue))
    │  async for event in event_generator(token_queue): yield SSE
    │
    ▼ (백그라운드 Task)
[graph.ainvoke(config={..., "token_queue": token_queue})]
    load_memory → rewrite_query → router
    → doc_search:  permission → retrieve → grade_documents → generate
    → web_search:  web_search → generate
    → generate_node: llm.stream(prompt) → queue.put(token) × N
                                         → queue.put(DONE_SENTINEL)
    → check_hallucination → save_memory → END
    (ainvoke 완료 후 stream_answer가 queue에 sources 이벤트, done 이벤트 삽입)
    (세션 저장: stream_answer가 session_store에 user/assistant 메시지 기록)
```

### SSE 이벤트 스키마

```
data: {"type": "token",   "content": "<token>"}   ← LLM 토큰마다
data: {"type": "sources", "sources": ["a.pdf"]}   ← 생성 완료 후 한 번
data: {"type": "done",    "session_id": "xxx"}     ← 스트림 종료 신호
data: {"type": "error",   "message": "..."}        ← 오류 발생 시
```

---

## 3. 백엔드 변경

### 3-1. `shared/llm/base.py`

`LLMClient` ABC에 추상 메서드 추가:

```python
from typing import AsyncIterator

@abstractmethod
async def stream(self, prompt: str) -> AsyncIterator[str]: ...
```

### 3-2. `shared/llm/anthropic_client.py`

- `anthropic.AsyncAnthropic` 클라이언트를 추가로 보유
- `stream()` 구현: `async_client.messages.stream()` → `text_stream` 이터레이터
- 기존 동기 `complete()`는 유지 (non-stream 경로 호환)

```python
async def stream(self, prompt: str) -> AsyncIterator[str]:
    async with self._async_client.messages.stream(
        model=self._model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    ) as s:
        async for text in s.text_stream:
            yield text
```

### 3-3. `shared/llm/openai_client.py`

`stream()` 구현: `AsyncOpenAI` + `chat.completions.create(stream=True)` → `delta.content` yield

### 3-4. `app/graph/nodes/generate.py`

`generate_node`를 `async def`로 변환. `RunnableConfig`에서 `token_queue` 추출:

```python
async def generate_node(state: dict, config: RunnableConfig | None = None) -> dict:
    queue: asyncio.Queue | None = (
        (config or {}).get("configurable", {}).get("token_queue")
    )
    ...
    if queue is not None:
        tokens = []
        async for token in llm.stream(prompt):
            tokens.append(token)
            await queue.put({"type": "token", "content": token})
        text = prefix + "".join(tokens)
    else:
        text = prefix + llm.complete(prompt)  # 기존 경로
    ...
    return {"answer": text, "citations": citations}
```

- `queue=None`일 때는 기존 동기 `llm.complete()` 경로 그대로 → 기존 `POST /chat` 호환 유지
- `_NO_DOC_NOTICE` prefix는 첫 토큰 전에 단일 토큰으로 큐에 삽입

### 3-5. `app/graph/builder.py`

`stream_answer()` 함수 추가:

```python
async def stream_answer(
    graph: CompiledStateGraph,
    question: str,
    config: dict,
    user_id: str,
    allowed_doc_ids: list[str],
    token_queue: asyncio.Queue,
) -> Answer:
    config["configurable"]["token_queue"] = token_queue
    final = await graph.ainvoke(initial_state, config=config)
    return Answer(text=final["answer"], sources=final["citations"])
```

`ainvoke` 완료 후 `stream_answer`가 직접:
1. `queue.put({"type":"sources", "sources":[...]})` 
2. `queue.put({"type":"done", "session_id":"..."})` 
삽입. `event_generator`는 `done` 이벤트 수신 시 스트림 종료.  
또한 `stream_answer` 완료 후 `session_store`에 user/assistant 메시지 기록 (`POST /chat`과 동일 로직, 예외는 로깅만).

### 3-6. `app/api/chat.py`

`POST /chat/stream` 엔드포인트 추가:

```python
@app.post("/chat/stream")
async def chat_stream(
    req: ChatRequest,
    request: Request,
    current_user: AuthUser = Depends(get_current_user),
    _: None = Depends(check_rate_limit),
) -> StreamingResponse:
    ...
    return StreamingResponse(
        event_generator(graph, req, current_user, session_store),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

`event_generator`는:
1. `asyncio.Queue` 생성
2. `asyncio.create_task(stream_answer(..., token_queue=queue))`
3. `queue.get()` 루프 → SSE `data: {...}\n\n` yield
4. `DONE_SENTINEL` 수신 시 sources/done 이벤트 yield 후 종료
5. 클라이언트 disconnect 감지 → Task 취소

---

## 4. 프론트엔드 변경

### 4-1. `web/src/types.ts`

```typescript
export type SSEEvent =
  | { type: "token";   content: string }
  | { type: "sources"; sources: string[] }
  | { type: "done";    session_id: string }
  | { type: "error";   message: string };
```

### 4-2. `web/src/api/client.ts`

`streamChat()` 추가 — `fetch` + `ReadableStream` 파싱:

```typescript
export async function* streamChat(
  question: string,
  sessionId: string | null
): AsyncGenerator<SSEEvent> {
  const token = localStorage.getItem("token");
  const res = await fetch(`${BASE_URL}/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ question, session_id: sessionId }),
  });

  if (res.status === 401) { onUnauthorized?.(); throw new ApiError(401, "Unauthorized"); }
  if (!res.ok) throw new ApiError(res.status, await safeMessage(res));

  const reader = res.body!.getReader();
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

### 4-3. `web/src/chat/ChatPage.tsx`

`send()` 함수를 스트리밍으로 교체:

```typescript
const send = async (question: string) => {
  const isNewSession = sessionId === null;
  setError(null);
  setPending(true);
  setMessages(prev => [...prev, { role: "user", content: question }]);
  // 빈 assistant 메시지 자리 확보
  setMessages(prev => [...prev, { role: "assistant", content: "", sources: [] }]);

  try {
    for await (const event of streamChat(question, sessionId)) {
      if (event.type === "token") {
        setMessages(prev => {
          const next = [...prev];
          next[next.length - 1] = {
            ...next[next.length - 1],
            content: next[next.length - 1].content + event.content,
          };
          return next;
        });
      } else if (event.type === "sources") {
        setMessages(prev => {
          const next = [...prev];
          next[next.length - 1] = { ...next[next.length - 1], sources: event.sources };
          return next;
        });
      } else if (event.type === "done") {
        setSessionId(event.session_id);
        if (isNewSession) getSessions().then(setSessions).catch(() => {});
      } else if (event.type === "error") {
        setError(event.message);
      }
    }
  } catch (err) {
    // ApiError 처리 (기존과 동일)
  } finally {
    setPending(false);
  }
};
```

---

## 5. 에러 처리

| 상황 | 처리 |
|---|---|
| `generate_node` 예외 | `queue.put({"type":"error",...})` 후 DONE_SENTINEL |
| 클라이언트 disconnect | `asyncio.Task.cancel()` |
| `check_hallucination` → 재생성 라우팅 | 두 번째 `generate_node` 실행 시 추가 토큰 스트리밍 |
| 401 / rate limit | SSE 이전에 HTTP 상태 코드로 응답 |

---

## 6. 테스트

| 대상 | 방법 |
|---|---|
| `AnthropicClient.stream()` | `AsyncAnthropic` mock, 토큰 시퀀스 검증 |
| `generate_node` (queue 있음) | 큐에 쌓인 토큰 순서 + 최종 state 검증 |
| `generate_node` (queue 없음) | 기존 동기 경로 regression |
| `POST /chat/stream` | TestClient SSE 이벤트 시퀀스 검증 |
| `streamChat()` | mock Response body, SSEEvent 타입 검증 |

---

## 7. 변경 파일 목록

**백엔드**
- `shared/llm/base.py` — `stream()` 추상 메서드 추가
- `shared/llm/anthropic_client.py` — `stream()` 구현, AsyncAnthropic 추가
- `shared/llm/openai_client.py` — `stream()` 구현
- `app/graph/nodes/generate.py` — async 전환, token_queue 분기
- `app/graph/builder.py` — `stream_answer()` 추가
- `app/api/chat.py` — `POST /chat/stream` 추가

**프론트엔드**
- `web/src/types.ts` — `SSEEvent` 타입 추가
- `web/src/api/client.ts` — `streamChat()` 추가
- `web/src/chat/ChatPage.tsx` — `send()` 스트리밍으로 교체

**테스트**
- `tests/shared/llm/test_anthropic_stream.py` (신규)
- `tests/app/graph/nodes/test_generate_stream.py` (신규)
- `tests/app/api/test_chat_stream.py` (신규)
- `web/src/api/client.test.ts` — `streamChat()` 케이스 추가
