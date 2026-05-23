import type { ChatMessage } from "../types";
import { SourceBadge } from "./SourceBadge";

export function MessageList({ messages }: { messages: ChatMessage[] }) {
  return (
    <div className="flex flex-col gap-3">
      {messages.map((msg, idx) => (
        <div
          key={idx}
          className={
            msg.role === "user"
              ? "self-end max-w-2xl bg-slate-800 text-white rounded-2xl px-4 py-2"
              : "self-start max-w-2xl bg-white border border-slate-200 rounded-2xl px-4 py-2"
          }
        >
          <p className="whitespace-pre-wrap">{msg.content}</p>
          {msg.role === "assistant" && msg.sources !== undefined && (
            <SourceBadge sources={msg.sources} />
          )}
        </div>
      ))}
    </div>
  );
}
