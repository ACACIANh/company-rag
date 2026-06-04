# Clarify UI 프론트엔드 연동 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `clarify_node`가 발행하는 interrupt payload를 SSE로 받아 한글 선택 버튼 카드를 렌더링하고, 사용자 선택을 resume 값으로 전송한다.

**Architecture:** 백엔드 `stream_answer`에서 interrupt payload에 `options` 키가 있으면 `type:"clarify"` SSE 이벤트로 분기. 프론트는 `ClarifyCard` 컴포넌트를 신규 추가하고, `awaitingClarify` 상태로 입력창을 비활성화. 사용자가 버튼 클릭 시 해당 한글 레이블을 `send(label)`로 전송해 그래프를 resume한다.

**Tech Stack:** React 18, TypeScript, Vitest + @testing-library/react, Python (FastAPI + LangGraph), Tailwind CSS

---

## File Map

| 파일 | 역할 | 변경 |
|------|------|------|
| `web/src/types.ts` | 타입 정의 | `ClarifyPayload` 인터페이스, `ChatMessage.clarify`, `SSEEvent` clarify 타입 추가 |
| `backend/app/graph/builder.py` | SSE 스트리밍 | `stream_answer` interrupt 분기, `_interrupt_answer` clarify 처리 |
| `web/src/chat/MessageList.tsx` | 메시지 렌더 | `ClarifyCard` 신규, `MessageList` props 확장 |
| `web/src/chat/MessageList.test.tsx` | MessageList 테스트 | ClarifyCard 테스트 추가 |
| `web/src/chat/MessageInput.tsx` | 입력 컴포넌트 | `awaitingClarify` prop 추가 |
| `web/src/chat/MessageInput.test.tsx` | MessageInput 테스트 | awaitingClarify 테스트 추가 |
| `web/src/chat/ChatPage.tsx` | 페이지 상태 | `awaitingClarify` 상태, clarify 이벤트 처리, `handleClarifySelect` |
| `web/src/chat/ChatPage.test.tsx` | ChatPage 테스트 | clarify 흐름 테스트 추가 |

---

## Task 1: types.ts 타입 추가

**Files:**
- Modify: `web/src/types.ts`

- [ ] **Step 1: 타입 변경**

`web/src/types.ts` 전체를 아래로 교체:

```typescript
export interface TokenRequest {
  username: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface AuthUser {
  user_id: string;
  roles: string[];
  departments: string[];
}

export interface ChatRequest {
  question: string;
  session_id: string | null;
}

export interface ChatResponse {
  answer: string;
  sources: string[];
  session_id: string;
}

export type ChatRole = "user" | "assistant";

export interface InterruptAction {
  tool: string;
  planned_action: string;
}

export interface ClarifyPayload {
  message: string;
  options: string[];
}

export interface ChatMessage {
  role: ChatRole;
  content: string;
  sources?: string[];
  route?: string;
  streaming?: boolean;
  interrupt?: InterruptAction[];
  clarify?: ClarifyPayload;
}

export class ApiError extends Error {
  status: number;
  retryAfter?: number;

  constructor(status: number, message: string, retryAfter?: number) {
    super(message);
    this.status = status;
    this.retryAfter = retryAfter;
  }
}

export interface Session {
  thread_id: string;
  title: string;
  created_at: string; // ISO8601
}

export interface SessionMessage {
  role: ChatRole;
  content: string;
  sources?: string[];
}

export type SSEEvent =
  | { type: "token";     content: string }
  | { type: "sources";   sources: string[]; route?: string }
  | { type: "done";      session_id: string }
  | { type: "error";     message: string }
  | { type: "interrupt"; actions: InterruptAction[] }
  | { type: "clarify";   message: string; options: string[] };
```

- [ ] **Step 2: TypeScript 타입 에러 없는지 확인**

```bash
cd /Users/acacian/vscode/company-rag/web
npm run build 2>&1 | grep -E "error|warning" | head -20
```
Expected: 기존 에러 없음 (빌드 성공)

- [ ] **Step 3: 커밋**

```bash
cd /Users/acacian/vscode/company-rag/web
git add src/types.ts
git commit -m "feat: ClarifyPayload 타입 추가, ChatMessage·SSEEvent 확장"
```

---

## Task 2: 백엔드 stream_answer clarify SSE 분기

**Files:**
- Modify: `backend/app/graph/builder.py`

현재 `stream_answer`의 interrupt 처리 (약 line 302–313):
```python
if "__interrupt__" in final:
    actions = final["__interrupt__"][0].value.get("actions", []) if isinstance(
        final["__interrupt__"][0].value, dict
    ) else []
    if is_new_session:
        ...
    await token_queue.put({"type": "interrupt", "actions": actions})
    await token_queue.put({"type": "done", "session_id": session_id})
    return
```

현재 `_interrupt_answer` (약 line 163–168):
```python
def _interrupt_answer(final: dict) -> Answer:
    intr = final["__interrupt__"][0].value
    actions = intr.get("actions", []) if isinstance(intr, dict) else []
    lines = "\n".join(f"- {a.get('tool')}: {a.get('planned_action')}" for a in actions)
    text = "이 작업은 사유 기재 후 실행됩니다. 실행하려면 사유를 회신하세요.\n" + lines
    return Answer(text=text, sources=[])
```

- [ ] **Step 1: `_interrupt_answer` 수정**

`backend/app/graph/builder.py`의 `_interrupt_answer` 함수를 아래로 교체:

```python
def _interrupt_answer(final: dict) -> Answer:
    intr = final["__interrupt__"][0].value if isinstance(
        final["__interrupt__"][0].value, dict
    ) else {}
    if "options" in intr:
        return Answer(
            text=f"{intr.get('message', '방식을 선택해주세요.')} (스트리밍 모드에서 선택 가능합니다.)",
            sources=[],
        )
    actions = intr.get("actions", [])
    lines = "\n".join(f"- {a.get('tool')}: {a.get('planned_action')}" for a in actions)
    text = "이 작업은 사유 기재 후 실행됩니다. 실행하려면 사유를 회신하세요.\n" + lines
    return Answer(text=text, sources=[])
```

- [ ] **Step 2: `stream_answer` interrupt 분기 수정**

`stream_answer`의 `if "__interrupt__" in final:` 블록을 아래로 교체 (is_new_session 세션 저장 로직은 유지):

```python
        if "__interrupt__" in final:
            intr_value = final["__interrupt__"][0].value if isinstance(
                final["__interrupt__"][0].value, dict
            ) else {}
            if is_new_session:
                try:
                    await session_store.create_session(session_id, user_id, question[:20])
                except Exception:
                    logging.exception("session store create failed for session_id=%s", session_id)
            if "options" in intr_value:
                await token_queue.put({
                    "type": "clarify",
                    "message": intr_value.get("message", ""),
                    "options": intr_value.get("options", []),
                })
            else:
                await token_queue.put({"type": "interrupt", "actions": intr_value.get("actions", [])})
            await token_queue.put({"type": "done", "session_id": session_id})
            return
```

- [ ] **Step 3: 백엔드 테스트 전체 pass 확인**

```bash
cd /Users/acacian/vscode/company-rag/backend
.venv/bin/python -m pytest tests/ -q --tb=short 2>&1 | tail -5
```
Expected: `495 passed` (기존 테스트 수 유지)

- [ ] **Step 4: 커밋**

```bash
cd /Users/acacian/vscode/company-rag/backend
git add app/graph/builder.py
git commit -m "feat: stream_answer clarify SSE 분기 추가 (ADR-0042)"
```

---

## Task 3: ClarifyCard 컴포넌트 (MessageList.tsx)

**Files:**
- Modify: `web/src/chat/MessageList.tsx`
- Modify: `web/src/chat/MessageList.test.tsx`

- [ ] **Step 1: 실패 테스트 작성**

`web/src/chat/MessageList.test.tsx` 하단에 추가:

```typescript
describe("MessageList clarify 카드", () => {
  const clarifyMsg: ChatMessage = {
    role: "assistant",
    content: "",
    clarify: {
      message: '"연차 어떻게 해?" — 어떤 방식으로 처리할까요?',
      options: ["사내 문서에서 찾기", "업무 DB 조회 / 권한 도구 사용"],
    },
  };

  it("메시지와 선택지 버튼 두 개를 렌더한다", () => {
    render(
      <MessageList
        messages={[clarifyMsg]}
        onCancel={vi.fn()}
        pending={false}
        awaitingJustification={false}
        onClarifySelect={vi.fn()}
        awaitingClarify={true}
      />
    );
    expect(screen.getByText(/어떤 방식으로 처리할까요/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "사내 문서에서 찾기" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "업무 DB 조회 / 권한 도구 사용" })).toBeInTheDocument();
  });

  it("버튼 클릭 시 onClarifySelect를 레이블과 함께 호출한다", () => {
    const onClarifySelect = vi.fn();
    render(
      <MessageList
        messages={[clarifyMsg]}
        onCancel={vi.fn()}
        pending={false}
        awaitingJustification={false}
        onClarifySelect={onClarifySelect}
        awaitingClarify={true}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: "사내 문서에서 찾기" }));
    expect(onClarifySelect).toHaveBeenCalledWith("사내 문서에서 찾기");
  });

  it("awaitingClarify=false이면 버튼이 비활성화된다", () => {
    render(
      <MessageList
        messages={[clarifyMsg]}
        onCancel={vi.fn()}
        pending={false}
        awaitingJustification={false}
        onClarifySelect={vi.fn()}
        awaitingClarify={false}
      />
    );
    expect(screen.getByRole("button", { name: "사내 문서에서 찾기" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "업무 DB 조회 / 권한 도구 사용" })).toBeDisabled();
  });
});
```

- [ ] **Step 2: 실패 확인**

```bash
cd /Users/acacian/vscode/company-rag/web
npm test 2>&1 | grep -E "FAIL|pass|fail" | tail -10
```
Expected: clarify 관련 테스트 3개 FAIL

- [ ] **Step 3: `ClarifyCard` 컴포넌트 구현 및 `MessageList` props 확장**

`web/src/chat/MessageList.tsx` 전체 교체:

```tsx
import { useCallback } from "react";
import type { ChatMessage } from "../types";
import { SourceBadge } from "./SourceBadge";
import { MarkdownRenderer } from "./MarkdownRenderer";

function CopyMessageButton({ content }: { content: string }) {
  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(content);
  }, [content]);

  return (
    <button
      onClick={handleCopy}
      className="mt-1 px-2 py-0.5 text-xs rounded text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors self-end"
    >
      Copy
    </button>
  );
}

function InterruptCard({
  actions,
  onCancel,
  pending,
  awaitingJustification,
}: {
  actions: NonNullable<ChatMessage["interrupt"]>;
  onCancel: () => void;
  pending: boolean;
  awaitingJustification: boolean;
}) {
  return (
    <div
      className="bg-canvas-cream border border-hairline rounded-xl px-4 py-3"
      style={{ boxShadow: "rgba(0,55,112,0.08) 0 1px 3px" }}
    >
      <p className="text-[13px] font-normal text-ruby mb-2">실행 승인이 필요합니다</p>
      <div className="flex flex-col gap-1.5 mb-3">
        {actions.map((a, i) => (
          <div key={i} className="flex flex-wrap items-center gap-1.5">
            <span className="text-[10px] font-normal bg-primary-muted text-primary-deep px-2 py-0.5 rounded-pill tracking-[0.1px]">
              {a.tool}
            </span>
            <span className="text-[13px] font-light text-ink">{a.planned_action}</span>
          </div>
        ))}
      </div>
      <div className="flex items-center justify-between">
        <p className="text-[12px] font-light text-ink-mute">
          실행하려면 사유를 입력하세요.
        </p>
        <button
          onClick={onCancel}
          disabled={pending || !awaitingJustification}
          className="text-[12px] font-normal text-ink-mute hover:text-ruby transition-colors px-2 py-0.5 disabled:opacity-40"
        >
          취소
        </button>
      </div>
    </div>
  );
}

function ClarifyCard({
  clarify,
  onSelect,
  disabled,
}: {
  clarify: NonNullable<ChatMessage["clarify"]>;
  onSelect: (label: string) => void;
  disabled: boolean;
}) {
  return (
    <div
      className="bg-canvas-cream border border-hairline rounded-xl px-4 py-3"
      style={{ boxShadow: "rgba(0,55,112,0.08) 0 1px 3px" }}
    >
      <p className="text-[13px] font-normal text-ink-mute mb-3">{clarify.message}</p>
      <div className="flex gap-2">
        {clarify.options.map((label) => (
          <button
            key={label}
            onClick={() => onSelect(label)}
            disabled={disabled}
            className="flex-1 px-3 py-2 text-[13px] font-normal rounded-lg border border-hairline bg-canvas hover:bg-primary-muted hover:text-primary-deep hover:border-primary transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}

export function MessageList({
  messages,
  onCancel,
  pending,
  awaitingJustification,
  onClarifySelect,
  awaitingClarify,
}: {
  messages: ChatMessage[];
  onCancel: () => void;
  pending: boolean;
  awaitingJustification: boolean;
  onClarifySelect: (label: string) => void;
  awaitingClarify: boolean;
}) {
  return (
    <div className="flex flex-col gap-4">
      {messages.map((msg, idx) => {
        if (msg.interrupt) {
          return (
            <div key={idx} className="self-start max-w-[85%]">
              <InterruptCard actions={msg.interrupt} onCancel={onCancel} pending={pending} awaitingJustification={awaitingJustification} />
            </div>
          );
        }
        if (msg.clarify) {
          return (
            <div key={idx} className="self-start max-w-[85%]">
              <ClarifyCard
                clarify={msg.clarify}
                onSelect={onClarifySelect}
                disabled={!awaitingClarify}
              />
            </div>
          );
        }
        return (
          <div
            key={idx}
            className={
              msg.role === "user"
                ? "self-end max-w-[75%]"
                : "self-start max-w-[85%]"
            }
          >
            <div
              className={
                msg.role === "user"
                  ? "bg-brand-dark text-canvas rounded-xl px-4 py-3 text-[15px] font-light"
                  : "bg-canvas border border-hairline rounded-xl px-4 py-3 text-[15px] font-light text-ink"
              }
              style={{
                boxShadow:
                  msg.role === "assistant"
                    ? "rgba(0,55,112,0.08) 0 1px 3px"
                    : undefined,
                fontFeatureSettings: '"ss01"',
              }}
            >
              {msg.role === "assistant" ? (
                <MarkdownRenderer content={msg.content} />
              ) : (
                <p className="whitespace-pre-wrap leading-[1.6]">{msg.content}</p>
              )}
            </div>
            {msg.role === "assistant" && !msg.streaming && (
              <div className="flex items-center justify-between mt-1 px-1">
                {msg.sources !== undefined && <SourceBadge sources={msg.sources} route={msg.route} />}
                <CopyMessageButton content={msg.content} />
              </div>
            )}
            {msg.role === "user" && (
              <div className="flex justify-end mt-1 px-1">
                <CopyMessageButton content={msg.content} />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 4: 테스트 pass 확인**

```bash
cd /Users/acacian/vscode/company-rag/web
npm test 2>&1 | grep -E "PASS|FAIL|passed|failed" | tail -10
```
Expected: 모든 테스트 PASS (기존 interrupt 테스트 포함)

- [ ] **Step 5: 커밋**

```bash
cd /Users/acacian/vscode/company-rag/web
git add src/chat/MessageList.tsx src/chat/MessageList.test.tsx
git commit -m "feat: ClarifyCard 컴포넌트 신규, MessageList props 확장"
```

---

## Task 4: MessageInput awaitingClarify prop 추가

**Files:**
- Modify: `web/src/chat/MessageInput.tsx`
- Modify: `web/src/chat/MessageInput.test.tsx`

- [ ] **Step 1: 실패 테스트 작성**

`web/src/chat/MessageInput.test.tsx` 하단에 추가:

```typescript
  it("awaitingClarify이면 선택 안내 placeholder로 바뀐다", () => {
    render(
      <MessageInput onSend={vi.fn()} disabled={false} awaitingClarify />
    );
    expect(
      screen.getByPlaceholderText("위에서 방식을 선택해주세요")
    ).toBeInTheDocument();
  });

  it("awaitingClarify이면 textarea가 비활성화된다", () => {
    render(
      <MessageInput onSend={vi.fn()} disabled={false} awaitingClarify />
    );
    expect(screen.getByRole("textbox")).toBeDisabled();
  });
```

(기존 `describe("MessageInput placeholder", () => {` 블록 안에 추가)

- [ ] **Step 2: 실패 확인**

```bash
cd /Users/acacian/vscode/company-rag/web
npm test -- --reporter=verbose 2>&1 | grep -E "✓|✗|×" | grep -i "clarify" | head -5
```
Expected: clarify 테스트 2개 FAIL

- [ ] **Step 3: MessageInput 구현**

`web/src/chat/MessageInput.tsx` 전체 교체:

```tsx
import { forwardRef, useImperativeHandle, useRef, useState } from "react";

interface Props {
  onSend: (text: string) => void;
  disabled: boolean;
  awaitingJustification?: boolean;
  awaitingClarify?: boolean;
}

export interface MessageInputHandle {
  focus: () => void;
}

export const MessageInput = forwardRef<MessageInputHandle, Props>(
  function MessageInput({ onSend, disabled, awaitingJustification, awaitingClarify }, ref) {
    const [text, setText] = useState("");
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    useImperativeHandle(ref, () => ({
      focus: () => textareaRef.current?.focus(),
    }));

    const isBlocked = disabled || !!awaitingClarify;

    const submit = () => {
      const trimmed = text.trim();
      if (!trimmed || isBlocked) return;
      onSend(trimmed);
      setText("");
    };

    const placeholder = awaitingClarify
      ? "위에서 방식을 선택해주세요"
      : awaitingJustification
      ? "실행 사유를 입력하세요"
      : "질문을 입력하세요. (Enter 전송, Shift+Enter 줄바꿈)";

    return (
      <div
        className="flex gap-3 bg-canvas border border-hairline rounded-xl px-4 py-3"
        style={{ boxShadow: "rgba(0,55,112,0.08) 0 1px 3px" }}
      >
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          rows={2}
          placeholder={placeholder}
          className="flex-1 resize-none bg-transparent text-ink text-[15px] font-light outline-none placeholder:text-ink-mute leading-[1.6]"
          style={{ fontFeatureSettings: '"ss01"' }}
          disabled={isBlocked}
        />
        <button
          onClick={submit}
          disabled={isBlocked || text.trim().length === 0}
          className="self-end bg-primary hover:bg-primary-deep active:bg-primary-press text-canvas font-normal text-[14px] rounded-pill px-4 py-1.5 transition-colors disabled:opacity-40"
        >
          전송
        </button>
      </div>
    );
  }
);
```

- [ ] **Step 4: 테스트 pass 확인**

```bash
cd /Users/acacian/vscode/company-rag/web
npm test 2>&1 | grep -E "PASS|FAIL|passed|failed" | tail -5
```
Expected: 모두 PASS

- [ ] **Step 5: 커밋**

```bash
cd /Users/acacian/vscode/company-rag/web
git add src/chat/MessageInput.tsx src/chat/MessageInput.test.tsx
git commit -m "feat: MessageInput awaitingClarify prop 추가"
```

---

## Task 5: ChatPage awaitingClarify 상태 연결

**Files:**
- Modify: `web/src/chat/ChatPage.tsx`
- Modify: `web/src/chat/ChatPage.test.tsx`

- [ ] **Step 1: 실패 테스트 작성**

`web/src/chat/ChatPage.test.tsx`에 새 describe 블록 추가 (기존 `describe("ChatPage interrupt(JUSTIFY) 흐름")` 아래):

```typescript
describe("ChatPage clarify 흐름", () => {
  beforeEach(() => {
    mockUseAuth.mockReturnValue({
      user: { user_id: "user-admin", roles: ["admin"], departments: [] },
      logout: vi.fn(),
    });
    vi.mocked(streamChat).mockReset();
    vi.mocked(getSessions).mockResolvedValue([]);
  });

  afterEach(() => {
    localStorage.clear();
  });

  it("clarify 이벤트 수신 시 선택지 버튼을 렌더한다", async () => {
    vi.mocked(streamChat).mockReturnValue(
      (async function* () {
        yield {
          type: "clarify",
          message: '"연차 어떻게 해?" — 어떤 방식으로 처리할까요?',
          options: ["사내 문서에서 찾기", "업무 DB 조회 / 권한 도구 사용"],
        };
        yield { type: "done", session_id: "s-1" };
      })()
    );

    render(<ChatPage />);
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "연차 어떻게 해?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "전송" }));

    expect(
      await screen.findByRole("button", { name: "사내 문서에서 찾기" })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "업무 DB 조회 / 권한 도구 사용" })
    ).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText("위에서 방식을 선택해주세요")
    ).toBeInTheDocument();
  });

  it("선택지 버튼 클릭 시 streamChat을 해당 레이블로 호출한다", async () => {
    vi.mocked(streamChat)
      .mockReturnValueOnce(
        (async function* () {
          yield {
            type: "clarify",
            message: '"연차 어떻게 해?" — 어떤 방식으로 처리할까요?',
            options: ["사내 문서에서 찾기", "업무 DB 조회 / 권한 도구 사용"],
          };
          yield { type: "done", session_id: "s-1" };
        })()
      )
      .mockReturnValueOnce(
        (async function* () {
          yield { type: "token", content: "연차 정책은..." };
          yield { type: "done", session_id: "s-1" };
        })()
      );

    render(<ChatPage />);
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "연차 어떻게 해?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "전송" }));

    const docBtn = await screen.findByRole("button", { name: "사내 문서에서 찾기" });
    fireEvent.click(docBtn);

    await waitFor(() => expect(streamChat).toHaveBeenCalledTimes(2));
    expect(streamChat).toHaveBeenLastCalledWith("사내 문서에서 찾기", "s-1");
    await waitFor(() =>
      expect(
        screen.getByPlaceholderText(/질문을 입력하세요/)
      ).toBeInTheDocument()
    );
  });

  it("clarify 대기 중 세션 전환 시 awaitingClarify가 해제된다", async () => {
    vi.mocked(getSessions).mockResolvedValue([
      { thread_id: "s-other", title: "다른 세션", created_at: "2026-06-03T00:00:00Z" },
    ]);
    vi.mocked(getSessionMessages).mockResolvedValue([
      { role: "user", content: "다른 질문", sources: [] },
    ]);
    vi.mocked(streamChat).mockReturnValue(
      (async function* () {
        yield {
          type: "clarify",
          message: '"연차?" — 방식을 선택하세요.',
          options: ["사내 문서에서 찾기", "업무 DB 조회 / 권한 도구 사용"],
        };
        yield { type: "done", session_id: "s-1" };
      })()
    );

    render(<ChatPage />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "연차?" } });
    fireEvent.click(screen.getByRole("button", { name: "전송" }));
    await screen.findByRole("button", { name: "사내 문서에서 찾기" });

    fireEvent.click(await screen.findByText("다른 세션"));

    await waitFor(() =>
      expect(screen.getByPlaceholderText(/질문을 입력하세요/)).toBeInTheDocument()
    );
  });
});
```

- [ ] **Step 2: 실패 확인**

```bash
cd /Users/acacian/vscode/company-rag/web
npm test 2>&1 | grep -E "FAIL|fail" | head -10
```
Expected: clarify 관련 테스트 3개 FAIL

- [ ] **Step 3: ChatPage 구현**

`web/src/chat/ChatPage.tsx`에서 다음 4가지를 수정:

**3-1. `awaitingClarify` 상태 추가** (line 17 `awaitingJustification` 바로 아래):

```tsx
const [awaitingClarify, setAwaitingClarify] = useState(false);
```

**3-2. `send` 함수 내 `setAwaitingJustification(false)` 바로 아래에 추가** (line 72):

```tsx
setAwaitingClarify(false);
```

**3-3. `event.type === "interrupt"` 블록 바로 아래에 clarify 블록 추가** (line 124 이후):

```tsx
} else if (event.type === "clarify") {
  setMessages((prev) => [
    ...prev,
    {
      role: "assistant",
      content: "",
      clarify: { message: event.message, options: event.options },
    },
  ]);
  setAwaitingClarify(true);
```

**3-4. `handleClarifySelect` 함수 추가** (`handleSelectSession` 함수 바로 위):

```tsx
const handleClarifySelect = (label: string) => {
  setAwaitingClarify(false);
  send(label);
};
```

**3-5. 세션 초기화 3곳에 `setAwaitingClarify(false)` 추가**

`handleSelectSession` (line 159 `setAwaitingJustification(false)` 아래):
```tsx
setAwaitingClarify(false);
```

`handleNewSession` (line 176 `setAwaitingJustification(false)` 아래):
```tsx
setAwaitingClarify(false);
```

`handleDeleteSession` (line 185 `setAwaitingJustification(false)` 아래):
```tsx
setAwaitingClarify(false);
```

**3-6. MessageList prop 전달 수정** (line 284):

```tsx
<MessageList
  messages={messages}
  onCancel={() => send("")}
  pending={pending}
  awaitingJustification={awaitingJustification}
  onClarifySelect={handleClarifySelect}
  awaitingClarify={awaitingClarify}
/>
```

**3-7. MessageInput prop 전달 수정** (line 308):

```tsx
<MessageInput
  ref={inputRef}
  onSend={send}
  disabled={pending || loadingHistory}
  awaitingJustification={awaitingJustification}
  awaitingClarify={awaitingClarify}
/>
```

- [ ] **Step 4: 전체 테스트 pass 확인**

```bash
cd /Users/acacian/vscode/company-rag/web
npm test 2>&1 | grep -E "PASS|FAIL|passed|failed" | tail -5
```
Expected: 모두 PASS

- [ ] **Step 5: 커밋**

```bash
cd /Users/acacian/vscode/company-rag/web
git add src/chat/ChatPage.tsx src/chat/ChatPage.test.tsx
git commit -m "feat: ChatPage awaitingClarify 상태 및 clarify SSE 이벤트 연결 (ADR-0042)"
```
