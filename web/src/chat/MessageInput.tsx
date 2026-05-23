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
    <div className="flex gap-2 border-t border-slate-200 p-3 bg-white">
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
        className="flex-1 resize-none rounded border border-slate-300 px-3 py-2"
        disabled={disabled}
      />
      <button
        onClick={submit}
        disabled={disabled || text.trim().length === 0}
        className="bg-slate-800 text-white rounded px-4 disabled:opacity-50"
      >
        전송
      </button>
    </div>
  );
}
