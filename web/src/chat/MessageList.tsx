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

export function MessageList({ messages }: { messages: ChatMessage[] }) {
  return (
    <div className="flex flex-col gap-4">
      {messages.map((msg, idx) => (
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
          {msg.role === "assistant" && (
            <div className="flex items-center justify-between mt-1 px-1">
              {msg.sources !== undefined && <SourceBadge sources={msg.sources} />}
              <CopyMessageButton content={msg.content} />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
