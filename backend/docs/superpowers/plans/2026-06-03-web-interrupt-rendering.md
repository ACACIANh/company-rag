# web interrupt(HITL JUSTIFY) 대화형 렌더링 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** web가 `/chat/stream`의 `{"type":"interrupt", actions}` SSE 이벤트를 대화형으로 렌더링하고, 기존 입력창으로 사유를 받아 resume하며, 빈 사유로 취소할 수 있게 한다.

**Architecture:** ADR-0030의 "대화형 렌더링" 결정을 따른다. interrupt를 특수 assistant 메시지(`interrupt` 필드 보유)로 표시하고, resume은 기존 `send`를 재사용한다(백엔드가 interrupt thread의 다음 메시지를 사유로 해석 — ADR-0024). resume 전용 엔드포인트·컴포넌트는 없다. 취소는 카드의 "취소" 버튼이 `send("")`를 직접 호출하고, 백엔드 `justify_execute`가 빈 사유를 취소로 처리한다(ADR-0027).

**Tech Stack:** Vite + React 18 + TypeScript + Tailwind, Vitest + @testing-library/react. 작업 디렉토리는 **`web/`**. 모든 명령은 `web/` 기준. 테스트 실행은 `npm test`(= `vitest run`).

**전제 — 검증 완료(2026-06-03):**
- `web/src/api/client.ts`의 `streamChat`은 `yield JSON.parse(line) as SSEEvent` — interrupt 이벤트를 그대로 yield하므로 **client.ts는 무변경**(타입만 확장).
- 백엔드 emit(`backend/app/graph/builder.py:272-278`): `{"type":"interrupt","actions":[...]}` 직후 `{"type":"done","session_id":...}`. 각 action은 `{tool, planned_action}`. interrupt 시 `token` 이벤트가 없으므로 ChatPage의 done 핸들러 `if (assistantAdded)` 블록은 실행되지 않고 `setSessionId(event.session_id)`만 수행 → **sessionId 보존됨**.
- MessageInput은 `text.trim()`이 빈 문자열이면 전송을 막으므로, 취소(빈 사유)는 입력창이 아니라 MessageList 카드 버튼이 ChatPage의 `send`를 직접 호출해야 한다.
- 색 토큰(`web/tailwind.config.js`): 경고 전용 토큰 없음. 경고 톤은 기존 `canvas-cream`(#f5e9d4) 배경 + `ruby`(#ea2261) 강조 + `hairline` 테두리로 표현.

---

## File Structure

| 파일 | 책임 | 변경 |
|------|------|------|
| `web/src/types.ts` | SSE/메시지 타입 | `InterruptAction` 추가, `SSEEvent`에 `interrupt` 분기, `ChatMessage.interrupt?` 추가 |
| `web/src/api/client.ts` | API 스트리밍 | **무변경**(타입만 확장되면 됨 — 작업 없음) |
| `web/src/chat/MessageList.tsx` | 메시지·interrupt 카드 렌더 | `msg.interrupt` 카드 + `onCancel` prop 추가 |
| `web/src/chat/MessageList.test.tsx` | MessageList 테스트 | **신규** |
| `web/src/chat/MessageInput.tsx` | 입력창 | `awaitingJustification` prop으로 placeholder 전환 |
| `web/src/chat/MessageInput.test.tsx` | MessageInput 테스트 | **신규** |
| `web/src/chat/ChatPage.tsx` | 스트림 루프·상태 오케스트레이션 | `send` 루프에 interrupt 케이스, `awaitingJustification` state, MessageList·MessageInput 배선 |
| `web/src/chat/ChatPage.test.tsx` | ChatPage 테스트 | interrupt 흐름 describe 추가 |

---

## Task 1: 타입 확장 — interrupt SSE 이벤트와 메시지 필드

**Files:**
- Modify: `web/src/types.ts:30-35` (ChatMessage), `web/src/types.ts:60-64` (SSEEvent)

이 task는 타입만 정의한다. 단위 테스트는 후속 task의 테스트가 컴파일·실행되며 검증하므로, 여기서는 `tsc` 통과로 검증한다.

- [ ] **Step 1: `InterruptAction` 인터페이스 추가**

`web/src/types.ts`의 `ChatMessage` 인터페이스 바로 위(현재 30번째 줄 `export type ChatRole` 아래, `export interface ChatMessage` 위)에 추가:

```ts
export interface InterruptAction {
  tool: string;
  planned_action: string;
}
```

- [ ] **Step 2: `ChatMessage`에 `interrupt?` 필드 추가**

`web/src/types.ts`의 `ChatMessage`를 다음으로 교체:

```ts
export interface ChatMessage {
  role: ChatRole;
  content: string;
  sources?: string[];
  streaming?: boolean;
  interrupt?: InterruptAction[]; // 있으면 JUSTIFY 안내 카드로 렌더
}
```

- [ ] **Step 3: `SSEEvent`에 `interrupt` 분기 추가**

`web/src/types.ts`의 `SSEEvent`를 다음으로 교체:

```ts
export type SSEEvent =
  | { type: "token";   content: string }
  | { type: "sources"; sources: string[] }
  | { type: "done";    session_id: string }
  | { type: "error";   message: string }
  | { type: "interrupt"; actions: InterruptAction[] };
```

- [ ] **Step 4: 타입 체크 통과 확인**

Run: `cd web && npx tsc --noEmit`
Expected: 에러 없음(exit 0). (기존 코드는 새 필드를 아직 안 쓰므로 통과해야 함)

- [ ] **Step 5: Commit**

```bash
cd web && git add src/types.ts
git commit -m "feat(web): interrupt SSE 이벤트·ChatMessage.interrupt 타입 추가 (ADR-0030)"
```

---

## Task 2: MessageList — interrupt 안내 카드 + 취소 버튼

**Files:**
- Test: `web/src/chat/MessageList.test.tsx` (신규)
- Modify: `web/src/chat/MessageList.tsx`

interrupt 필드를 가진 메시지는 일반 말풍선 대신 경고 톤 카드로 렌더한다: 계획된 동작 목록(`tool` + `planned_action`), "실행하려면 사유를 입력하세요" 안내, "취소" 버튼. 취소 버튼은 `onCancel` prop을 호출한다.

- [ ] **Step 1: 실패 테스트 작성**

`web/src/chat/MessageList.test.tsx` 생성:

```tsx
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { MessageList } from "./MessageList";
import type { ChatMessage } from "../types";

describe("MessageList interrupt 카드", () => {
  const interruptMsg: ChatMessage = {
    role: "assistant",
    content: "",
    interrupt: [
      { tool: "manage_permission", planned_action: "grant user:alice member department:finance" },
    ],
  };

  it("계획된 동작(tool·planned_action)을 렌더한다", () => {
    render(<MessageList messages={[interruptMsg]} onCancel={vi.fn()} />);
    expect(screen.getByText(/manage_permission/)).toBeInTheDocument();
    expect(
      screen.getByText(/grant user:alice member department:finance/)
    ).toBeInTheDocument();
  });

  it("사유 입력 안내를 렌더한다", () => {
    render(<MessageList messages={[interruptMsg]} onCancel={vi.fn()} />);
    expect(screen.getByText(/사유를 입력/)).toBeInTheDocument();
  });

  it("취소 버튼 클릭 시 onCancel을 호출한다", () => {
    const onCancel = vi.fn();
    render(<MessageList messages={[interruptMsg]} onCancel={onCancel} />);
    fireEvent.click(screen.getByRole("button", { name: "취소" }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("interrupt가 없는 일반 assistant 메시지는 카드를 렌더하지 않는다", () => {
    render(
      <MessageList
        messages={[{ role: "assistant", content: "일반 답변", sources: [] }]}
        onCancel={vi.fn()}
      />
    );
    expect(screen.queryByText(/사유를 입력/)).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd web && npx vitest run src/chat/MessageList.test.tsx`
Expected: FAIL — `MessageList`가 `onCancel` prop을 받지 않고 interrupt 카드를 렌더하지 않으므로 "사유를 입력"·"취소" 탐색 실패.

- [ ] **Step 3: MessageList 구현**

`web/src/chat/MessageList.tsx`를 다음으로 교체(props에 `onCancel` 추가, map 안에서 `msg.interrupt` 분기 추가):

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
}: {
  actions: NonNullable<ChatMessage["interrupt"]>;
  onCancel: () => void;
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
          className="text-[12px] font-normal text-ink-mute hover:text-ruby transition-colors px-2 py-0.5"
        >
          취소
        </button>
      </div>
    </div>
  );
}

export function MessageList({
  messages,
  onCancel,
}: {
  messages: ChatMessage[];
  onCancel: () => void;
}) {
  return (
    <div className="flex flex-col gap-4">
      {messages.map((msg, idx) => {
        if (msg.interrupt) {
          return (
            <div key={idx} className="self-start max-w-[85%]">
              <InterruptCard actions={msg.interrupt} onCancel={onCancel} />
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
                {msg.sources !== undefined && <SourceBadge sources={msg.sources} />}
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

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd web && npx vitest run src/chat/MessageList.test.tsx`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
cd web && git add src/chat/MessageList.tsx src/chat/MessageList.test.tsx
git commit -m "feat(web): MessageList interrupt 안내 카드·취소 버튼 (ADR-0030)"
```

---

## Task 3: MessageInput — awaitingJustification placeholder 전환

**Files:**
- Test: `web/src/chat/MessageInput.test.tsx` (신규)
- Modify: `web/src/chat/MessageInput.tsx`

`awaitingJustification` prop이 true면 placeholder를 "실행 사유를 입력하세요"로 바꿔 모드 전환을 시각화한다. 전송 로직은 불변.

- [ ] **Step 1: 실패 테스트 작성**

`web/src/chat/MessageInput.test.tsx` 생성:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { MessageInput } from "./MessageInput";

describe("MessageInput placeholder", () => {
  it("기본 placeholder는 질문 안내를 보여준다", () => {
    render(<MessageInput onSend={vi.fn()} disabled={false} />);
    expect(
      screen.getByPlaceholderText(/질문을 입력하세요/)
    ).toBeInTheDocument();
  });

  it("awaitingJustification이면 사유 입력 placeholder로 바뀐다", () => {
    render(
      <MessageInput onSend={vi.fn()} disabled={false} awaitingJustification />
    );
    expect(
      screen.getByPlaceholderText("실행 사유를 입력하세요")
    ).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd web && npx vitest run src/chat/MessageInput.test.tsx`
Expected: FAIL — `MessageInput`이 `awaitingJustification` prop을 모르고 placeholder가 고정이라 두 번째 테스트가 실패.

- [ ] **Step 3: MessageInput 구현**

`web/src/chat/MessageInput.tsx`를 다음으로 교체(Props에 `awaitingJustification?` 추가, placeholder 분기):

```tsx
import { useState } from "react";

interface Props {
  onSend: (text: string) => void;
  disabled: boolean;
  awaitingJustification?: boolean;
}

export function MessageInput({ onSend, disabled, awaitingJustification }: Props) {
  const [text, setText] = useState("");

  const submit = () => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setText("");
  };

  return (
    <div
      className="flex gap-3 bg-canvas border border-hairline rounded-xl px-4 py-3"
      style={{ boxShadow: "rgba(0,55,112,0.08) 0 1px 3px" }}
    >
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        }}
        rows={2}
        placeholder={
          awaitingJustification
            ? "실행 사유를 입력하세요"
            : "질문을 입력하세요. (Enter 전송, Shift+Enter 줄바꿈)"
        }
        className="flex-1 resize-none bg-transparent text-ink text-[15px] font-light outline-none placeholder:text-ink-mute leading-[1.6]"
        style={{ fontFeatureSettings: '"ss01"' }}
        disabled={disabled}
      />
      <button
        onClick={submit}
        disabled={disabled || text.trim().length === 0}
        className="self-end bg-primary hover:bg-primary-deep active:bg-primary-press text-canvas font-normal text-[14px] rounded-pill px-4 py-1.5 transition-colors disabled:opacity-40"
      >
        전송
      </button>
    </div>
  );
}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd web && npx vitest run src/chat/MessageInput.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
cd web && git add src/chat/MessageInput.tsx src/chat/MessageInput.test.tsx
git commit -m "feat(web): MessageInput awaitingJustification placeholder 전환 (ADR-0030)"
```

---

## Task 4: ChatPage — interrupt 케이스·awaitingJustification 상태·배선

**Files:**
- Modify: `web/src/chat/ChatPage.tsx` (state 추가, `send` 루프, MessageList·MessageInput props)
- Test: `web/src/chat/ChatPage.test.tsx` (interrupt describe 추가)

`send` 루프에 interrupt 케이스를 추가해 특수 메시지를 push하고 `awaitingJustification`을 켠다. `send` 시작부에서 끈다(다음 회신이 resume이든 신규 질문이든 백엔드가 thread 상태로 판단). 취소는 `send("")`. MessageList에 `onCancel={() => send("")}`, MessageInput에 `awaitingJustification`을 전달.

- [ ] **Step 1: 실패 테스트 작성**

`web/src/chat/ChatPage.test.tsx` 끝에 describe 블록을 추가하고, 파일 상단 import에 `fireEvent`를 추가한다. 먼저 첫 줄 import를 다음으로 교체:

```tsx
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
```

그리고 파일 맨 끝에 추가:

```tsx
describe("ChatPage interrupt(JUSTIFY) 흐름", () => {
  beforeEach(() => {
    mockUseAuth.mockReturnValue({
      user: { user_id: "user-admin", roles: ["admin"], departments: [] },
      logout: vi.fn(),
    });
    vi.mocked(streamChat).mockReset();
  });

  afterEach(() => {
    localStorage.clear();
  });

  it("interrupt 이벤트 수신 시 안내 카드를 렌더하고 사유 입력 모드로 전환한다", async () => {
    vi.mocked(streamChat).mockReturnValue(
      (async function* () {
        yield {
          type: "interrupt",
          actions: [
            { tool: "manage_permission", planned_action: "grant user:alice member department:finance" },
          ],
        };
        yield { type: "done", session_id: "s-1" };
      })()
    );

    render(<ChatPage />);
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "alice를 finance에 추가해줘" },
    });
    fireEvent.click(screen.getByRole("button", { name: "전송" }));

    expect(
      await screen.findByText(/grant user:alice member department:finance/)
    ).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText("실행 사유를 입력하세요")
    ).toBeInTheDocument();
  });

  it("사유를 전송하면 streamChat을 다시 호출하고 사유 입력 모드를 해제한다", async () => {
    vi.mocked(streamChat)
      .mockReturnValueOnce(
        (async function* () {
          yield {
            type: "interrupt",
            actions: [{ tool: "manage_permission", planned_action: "grant ..." }],
          };
          yield { type: "done", session_id: "s-1" };
        })()
      )
      .mockReturnValueOnce(
        (async function* () {
          yield { type: "token", content: "실행했습니다" };
          yield { type: "done", session_id: "s-1" };
        })()
      );

    render(<ChatPage />);
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "alice를 finance에 추가해줘" },
    });
    fireEvent.click(screen.getByRole("button", { name: "전송" }));
    await screen.findByText(/grant/);

    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "감사 대응을 위해 필요합니다" },
    });
    fireEvent.click(screen.getByRole("button", { name: "전송" }));

    await waitFor(() => expect(streamChat).toHaveBeenCalledTimes(2));
    expect(streamChat).toHaveBeenLastCalledWith(
      "감사 대응을 위해 필요합니다",
      "s-1"
    );
    await waitFor(() =>
      expect(
        screen.getByPlaceholderText(/질문을 입력하세요/)
      ).toBeInTheDocument()
    );
  });

  it("취소 버튼은 빈 사유로 streamChat을 호출한다", async () => {
    vi.mocked(streamChat)
      .mockReturnValueOnce(
        (async function* () {
          yield {
            type: "interrupt",
            actions: [{ tool: "manage_permission", planned_action: "grant ..." }],
          };
          yield { type: "done", session_id: "s-1" };
        })()
      )
      .mockReturnValueOnce((async function* () {})());

    render(<ChatPage />);
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "alice를 finance에 추가해줘" },
    });
    fireEvent.click(screen.getByRole("button", { name: "전송" }));
    await screen.findByText(/grant/);

    fireEvent.click(screen.getByRole("button", { name: "취소" }));

    await waitFor(() => expect(streamChat).toHaveBeenCalledTimes(2));
    expect(streamChat).toHaveBeenLastCalledWith("", "s-1");
  });
});
```

> 참고: `streamChat`는 이미 파일 상단에서 `vi.mock("../api/client", ...)`로 모킹되어 있다. import 목록에 `streamChat`가 없으면 `import { getSessionMessages, streamChat } from "../api/client";`로 보강한다.

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd web && npx vitest run src/chat/ChatPage.test.tsx`
Expected: FAIL — interrupt 케이스가 없어 카드가 렌더되지 않고, MessageList가 `onCancel` 없이 호출돼 타입/렌더 에러, placeholder 미전환.

- [ ] **Step 3: ChatPage `send` 루프에 interrupt 케이스·state 추가**

`web/src/chat/ChatPage.tsx`에서 `pending` state 선언(현재 16번째 줄 `const [pending, setPending] = useState(false);`) 바로 아래에 추가:

```tsx
  const [awaitingJustification, setAwaitingJustification] = useState(false);
```

`send` 함수 시작부(`setError(null);` 위)에 사유 모드 해제를 추가. 현재:

```tsx
  const send = async (question: string) => {
    isNearBottomRef.current = true;
    const isNewSession = sessionId === null;
    setError(null);
```

를 다음으로 교체:

```tsx
  const send = async (question: string) => {
    isNearBottomRef.current = true;
    const isNewSession = sessionId === null;
    setAwaitingJustification(false);
    setError(null);
```

`send` 루프 안 `else if (event.type === "error")` 블록 **앞**에 interrupt 케이스를 추가. 현재:

```tsx
        } else if (event.type === "error") {
          setError(event.message);
        }
```

를 다음으로 교체:

```tsx
        } else if (event.type === "interrupt") {
          setMessages((prev) => [
            ...prev,
            { role: "assistant", content: "", interrupt: event.actions },
          ]);
          setAwaitingJustification(true);
        } else if (event.type === "error") {
          setError(event.message);
        }
```

> 주의: 빈 사유 전송 시에도 user 메시지("")가 push된다. 취소 흐름에서 빈 user 말풍선이 보이지 않도록, user 메시지 push를 빈 문자열일 때 건너뛴다. 현재 68번째 줄:
>
> ```tsx
>     setMessages((prev) => [...prev, { role: "user", content: question }]);
> ```
>
> 를 다음으로 교체:
>
> ```tsx
>     if (question !== "") {
>       setMessages((prev) => [...prev, { role: "user", content: question }]);
>     }
> ```

- [ ] **Step 4: MessageList·MessageInput 배선**

`ChatPage.tsx`의 `<MessageList messages={messages} />`(현재 266번째 줄)를 교체:

```tsx
              <MessageList messages={messages} onCancel={() => send("")} />
```

`<MessageInput onSend={send} disabled={pending || loadingHistory} />`(현재 290번째 줄)를 교체:

```tsx
            <MessageInput
              onSend={send}
              disabled={pending || loadingHistory}
              awaitingJustification={awaitingJustification}
            />
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd web && npx vitest run src/chat/ChatPage.test.tsx`
Expected: PASS (기존 5개 + 신규 3개).

- [ ] **Step 6: 전체 테스트·타입 체크**

Run: `cd web && npx tsc --noEmit && npm test`
Expected: 타입 에러 없음, 전체 테스트 PASS.

- [ ] **Step 7: Commit**

```bash
cd web && git add src/chat/ChatPage.tsx src/chat/ChatPage.test.tsx
git commit -m "feat(web): ChatPage interrupt 케이스·사유 입력 모드·취소 배선 (ADR-0030)"
```

---

## Task 5: 수동 검증 · ADR 상태 갱신 · 인덱스 재생성

**Files:**
- Modify: `backend/docs/superpowers/decisions/ADR-0030-web-interrupt-rendering.md:3` (Status)
- Regenerate: `backend/docs/superpowers/decisions/README.md` (스크립트 자동 생성)

- [ ] **Step 1: 수동 검증(선택, 환경 가능 시)**

백엔드(`cd backend && .venv/bin/python -m uvicorn app.main:app`)와 web(`cd web && npm run dev`)을 띄우고:
1. admin 계정 로그인.
2. 권한 부여 질문(예: "alice를 finance 부서에 추가해줘") 전송 → interrupt 안내 카드 + tool/planned_action 노출 + 입력창 placeholder "실행 사유를 입력하세요" 확인.
3. 사유 입력·전송 → 실행 결과 응답, placeholder 원복 확인.
4. 다시 유발 후 "취소" 버튼 → 취소 처리(빈 사유) 확인.

자동화 테스트(Task 2~4)로 회귀는 커버되므로, 환경 미가용 시 이 단계는 생략하고 그 사실을 기록한다.

- [ ] **Step 2: ADR-0030 Status를 적용완료로 변경**

`backend/docs/superpowers/decisions/ADR-0030-web-interrupt-rendering.md`의 3번째 줄을 교체:

```
> **Status**: ⚪ 제안됨   <!-- 🟢 적용완료 · 🔵 승인됨 · ⚪ 제안됨 · 🟡 보류 · 🟣 대체됨 · ⚫ 폐기 -->
```

를:

```
> **Status**: 🟢 적용완료   <!-- 🟢 적용완료 · 🔵 승인됨 · ⚪ 제안됨 · 🟡 보류 · 🟣 대체됨 · ⚫ 폐기 -->
```

- [ ] **Step 3: ADR 인덱스 재생성**

Run: `cd backend && .venv/bin/python -m scripts.gen_adr_index`
Expected: `decisions/README.md` 재생성, ADR-0030 상태가 적용완료로 반영.

- [ ] **Step 4: Commit**

```bash
cd /Users/acacian/vscode/company-rag
git add backend/docs/superpowers/decisions/ADR-0030-web-interrupt-rendering.md backend/docs/superpowers/decisions/README.md
git commit -m "docs(adr): ADR-0030 적용완료 — web interrupt 대화형 렌더링 구현"
```

---

## Self-Review (작성자 점검 완료)

**Spec coverage(ADR-0030 구현 범위 ①~⑥ → task):**
- ① 타입(types.ts) → Task 1 ✓
- ② API(client.ts 무변경) → File Structure에 "무변경" 명시, 별도 task 불필요 ✓
- ③ ChatPage(awaitingJustification·interrupt 케이스·resume 전용 코드 없음) → Task 4 ✓
- ④ MessageList(경고 카드·계획 동작·취소 버튼) → Task 2 ✓
- ⑤ MessageInput(placeholder 전환) → Task 3 ✓
- ⑥ 취소=빈 사유(`send("")`) → Task 4 Step 3/4(onCancel 배선) ✓
- DoD 1~3(컴포넌트 테스트) → Task 2~4 테스트 ✓ / DoD 4(수동검증) → Task 5 Step 1 ✓ / DoD 5(인덱스 재생성) → Task 5 Step 3 ✓

**Placeholder scan:** 모든 코드 step에 완전한 코드 블록 수록. "TODO/적절히 처리" 류 없음 ✓

**Type consistency:** `InterruptAction{tool, planned_action}`(Task 1)이 MessageList 카드(Task 2)·ChatPage push(Task 4)·테스트 fixture와 키 일치. `onCancel: () => void`(Task 2 props)와 ChatPage `onCancel={() => send("")}`(Task 4) 시그니처 일치. `awaitingJustification?`(Task 3 props)와 ChatPage 전달(Task 4) 일치 ✓

**보강 결정(설계 대비 추가):** 취소 시 빈 user 말풍선이 보이지 않도록 ChatPage `send`에서 `question !== ""`일 때만 user 메시지를 push하도록 했다(Task 4 Step 3 주의). ADR 본문에 없던 UX 디테일이나, "취소=빈 사유 send" 결정의 자연스러운 귀결이며 변경 표면 최소 원칙에 부합.
