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
