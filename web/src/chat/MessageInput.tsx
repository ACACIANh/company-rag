import { useState } from "react";

interface Props {
  onSend: (text: string) => void;
  disabled: boolean;
}

export function MessageInput({ onSend, disabled }: Props) {
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
        placeholder="질문을 입력하세요. (Enter 전송, Shift+Enter 줄바꿈)"
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
