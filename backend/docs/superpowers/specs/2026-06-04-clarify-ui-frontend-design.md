# 설계: clarify UI 프론트엔드 연동

## 목표

백엔드 `clarify_node`가 발행하는 interrupt payload를 프론트엔드에서 한글 선택 버튼 카드로 렌더링하고, 사용자가 선택한 레이블을 resume 값으로 전송한다.

---

## 1. 전체 데이터 흐름

```
router_node (confidence < 0.75)
  → route="clarify"
  → clarify_node: interrupt({"message": "...", "options": [...]})
  → 백엔드 SSE: {"type":"clarify","message":"...","options":["사내 문서에서 찾기","업무 DB 조회 / 권한 도구 사용"]}
  → 프론트: ClarifyCard 렌더링 (인라인 버튼 카드, Option A)
  → 사용자 버튼 클릭 → send(label) → graph resume
  → 해당 경로(doc_search | agent) 재개
```

기존 JUSTIFY 흐름(`{ type: "interrupt", actions: [...] }`)과 **독립적인 새 SSE 타입** `"clarify"`로 분리한다.

---

## 2. 변경 파일 목록

| 레이어 | 파일 | 변경 |
|--------|------|------|
| 백엔드 | `app/graph/builder.py` | `_interrupt_answer`, `stream_answer`에서 clarify payload 감지 → `type:"clarify"` SSE 전송 |
| 백엔드 스키마 | `app/api/models.py` (또는 Answer 정의 위치) | `Answer`에 `clarify` 필드 추가 |
| 프론트 타입 | `web/src/types.ts` | `SSEEvent`에 clarify 타입 추가, `ChatMessage`에 `clarify` 필드 추가 |
| 프론트 상태 | `web/src/chat/ChatPage.tsx` | `awaitingClarify` 상태, clarify 이벤트 처리, `handleClarifySelect` |
| 프론트 UI | `web/src/chat/MessageList.tsx` | `ClarifyCard` 컴포넌트 신규 |
| 프론트 UI | `web/src/chat/MessageInput.tsx` | `awaitingClarify` prop 추가 — 비활성화 |

---

## 3. 백엔드 SSE 변경

### `_interrupt_answer` (비스트리밍)

```python
def _interrupt_answer(final: dict) -> Answer:
    intr = final["__interrupt__"][0].value
    if "options" in intr:
        return Answer(
            clarify={"message": intr["message"], "options": intr["options"]},
            text="", sources=[]
        )
    # 기존 JUSTIFY 경로
    actions = [
        {"tool": p["name"], "planned_action": p["planned_action"], "risk": p["risk"]}
        for p in intr.get("actions", [])
    ]
    return Answer(interrupt=actions, text="", sources=[])
```

### `stream_answer` SSE 전송부

```python
intr_value = task.interrupts[0].value
if "options" in intr_value:
    payload = json.dumps({
        "type": "clarify",
        "message": intr_value["message"],
        "options": intr_value["options"],
    }, ensure_ascii=False)
    await token_queue.put(f"data: {payload}\n\n")
else:
    # 기존 interrupt actions 전송
    ...
```

### `Answer` 스키마

`core/models.py`의 `Answer`는 dataclass로 interrupt 필드가 없고, SSE 스트리밍 경로에서 직접 token_queue로 이벤트를 전송한다. `Answer` 스키마 변경 불필요.

비스트리밍 `_interrupt_answer`는 clarify 시 단순 안내 텍스트만 반환:

```python
def _interrupt_answer(final: dict) -> Answer:
    intr = final["__interrupt__"][0].value if isinstance(
        final["__interrupt__"][0].value, dict) else {}
    if "options" in intr:
        return Answer(
            text=f"{intr.get('message', '')} — 스트리밍 모드에서 선택해주세요.",
            sources=[]
        )
    # 기존 JUSTIFY 경로 유지
    ...
```

---

## 4. 프론트엔드 타입

### `web/src/types.ts`

```typescript
// SSEEvent에 추가
| { type: "clarify"; message: string; options: string[] }

// ChatMessage에 추가
clarify?: { message: string; options: string[] }
```

---

## 5. 프론트엔드 상태 (`ChatPage.tsx`)

```typescript
const [awaitingClarify, setAwaitingClarify] = useState(false);

// SSE 이벤트 처리
} else if (event.type === "clarify") {
  setMessages(prev => [...prev, {
    role: "assistant",
    content: "",
    clarify: { message: event.message, options: event.options },
  }]);
  setAwaitingClarify(true);
}

// 선택 핸들러 — 한글 레이블을 resume 값으로 전송
const handleClarifySelect = async (label: string) => {
  setAwaitingClarify(false);
  await send(label);
};
```

세션 전환·삭제·새 세션 생성 시 `setAwaitingClarify(false)` 초기화 (기존 `awaitingJustification` 패턴 동일 위치에 추가).

`handleClarifySelect`를 `MessageList`에 prop으로 전달.

---

## 6. UI 컴포넌트

### `ClarifyCard` (`MessageList.tsx`)

```tsx
function ClarifyCard({ clarify, onSelect, disabled }: {
  clarify: NonNullable<ChatMessage["clarify"]>;
  onSelect: (label: string) => void;
  disabled: boolean;
}) {
  return (
    <div className="interrupt-card">
      <p className="interrupt-message">{clarify.message}</p>
      <div className="clarify-options">
        {clarify.options.map(label => (
          <button
            key={label}
            className="clarify-btn"
            onClick={() => onSelect(label)}
            disabled={disabled}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}
```

메시지 렌더링부:

```tsx
if (msg.clarify) {
  return (
    <ClarifyCard
      clarify={msg.clarify}
      onSelect={onClarifySelect}
      disabled={!awaitingClarify}   // 가장 최근 카드만 활성(awaitingClarify=true), 이전 카드 비활성
    />
  );
}
```

### `MessageInput.tsx`

```tsx
// props 추가
awaitingClarify?: boolean;

// 기존 awaitingJustification과 OR 조건
const isBlocked = awaitingJustification || !!awaitingClarify;

<textarea
  disabled={isBlocked}
  placeholder={
    awaitingClarify
      ? "위에서 방식을 선택해주세요"
      : awaitingJustification
      ? "실행 사유를 입력하세요"
      : "질문을 입력하세요. (Enter 전송, Shift+Enter 줄바꿈)"
  }
/>
```

---

## 7. 테스트

| 파일 | 테스트 케이스 |
|------|--------------|
| `MessageList.test.tsx` | ClarifyCard 렌더링, 버튼 클릭 → onSelect 호출, disabled 상태 |
| `ChatPage.test.tsx` | clarify SSE 이벤트 수신 → awaitingClarify=true, 버튼 클릭 → send(label) 호출, 세션 전환 시 초기화 |
| `MessageInput.test.tsx` | awaitingClarify=true → disabled + placeholder 변경 |
