import { useEffect, useState } from "react";
import { apiFetch } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { ApiError } from "../types";
import type { ChatMessage, ChatResponse } from "../types";
import { MessageInput } from "./MessageInput";
import { MessageList } from "./MessageList";

export function ChatPage() {
  const { user, logout } = useAuth();
  const [sessionId, setSessionId] = useState<string | null>(() =>
    localStorage.getItem("session_id")
  );
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (sessionId) localStorage.setItem("session_id", sessionId);
  }, [sessionId]);

  const send = async (question: string) => {
    setError(null);
    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setPending(true);
    try {
      const res = await apiFetch<ChatResponse>("/chat", {
        method: "POST",
        body: { question, session_id: sessionId },
      });
      setSessionId(res.session_id);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: res.answer, sources: res.sources },
      ]);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 429 && err.retryAfter !== undefined) {
          setError(`요청이 많습니다. ${err.retryAfter}초 후 다시 시도하세요.`);
        } else if (err.status !== 401) {
          setError(err.message || "요청 처리 중 오류가 발생했습니다.");
        }
      } else {
        setError("네트워크 오류가 발생했습니다.");
      }
    } finally {
      setPending(false);
    }
  };

  const handleLogout = () => {
    setMessages([]);
    setSessionId(null);
    logout();
  };

  return (
    <div className="min-h-screen flex flex-col bg-canvas-soft">
      {/* nav-bar-on-mesh */}
      <header className="flex items-center justify-between border-b border-hairline bg-canvas px-6 py-3"
        style={{ boxShadow: "rgba(0,55,112,0.08) 0 1px 3px" }}
      >
        <h1
          className="text-[20px] font-light text-ink tracking-[-0.2px]"
          style={{ fontFeatureSettings: '"ss01"' }}
        >
          Company RAG
        </h1>
        <div className="flex items-center gap-4">
          <span className="text-[13px] text-ink-mute font-normal tracking-[-0.39px]">
            {user?.user_id ?? ""}
          </span>
          <button
            onClick={handleLogout}
            className="text-[14px] font-normal text-primary hover:text-primary-deep transition-colors"
          >
            로그아웃
          </button>
        </div>
      </header>

      <main className="flex-1 overflow-y-auto px-4 py-6 max-w-3xl w-full mx-auto">
        <MessageList messages={messages} />
        {pending && (
          <div className="flex items-center gap-2 mt-4">
            <span className="flex gap-1">
              {[0, 1, 2].map((i) => (
                <span
                  key={i}
                  className="w-1.5 h-1.5 rounded-pill bg-primary-muted animate-bounce"
                  style={{ animationDelay: `${i * 0.15}s` }}
                />
              ))}
            </span>
            <span className="text-[13px] text-ink-mute font-normal">답변 생성 중…</span>
          </div>
        )}
        {error && (
          <p className="text-[13px] text-ruby font-normal mt-3">{error}</p>
        )}
      </main>

      <div className="max-w-3xl w-full mx-auto px-4 pb-4">
        <MessageInput onSend={send} disabled={pending} />
      </div>
    </div>
  );
}
