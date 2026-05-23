import type { ChatMessage } from "../types";
import { SourceBadge } from "./SourceBadge";

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
            <p className="whitespace-pre-wrap leading-[1.6]">{msg.content}</p>
          </div>
          {msg.role === "assistant" && msg.sources !== undefined && (
            <div className="mt-2 px-1">
              <SourceBadge sources={msg.sources} />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
