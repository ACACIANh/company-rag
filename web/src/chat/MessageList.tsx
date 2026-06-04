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
}: {
  actions: NonNullable<ChatMessage["interrupt"]>;
  onCancel: () => void;
  pending: boolean;
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
          disabled={pending}
          className="text-[12px] font-normal text-ink-mute hover:text-ruby transition-colors px-2 py-0.5 disabled:opacity-40"
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
  pending,
}: {
  messages: ChatMessage[];
  onCancel: () => void;
  pending: boolean;
}) {
  return (
    <div className="flex flex-col gap-4">
      {messages.map((msg, idx) => {
        if (msg.interrupt) {
          return (
            <div key={idx} className="self-start max-w-[85%]">
              <InterruptCard actions={msg.interrupt} onCancel={onCancel} pending={pending} />
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
