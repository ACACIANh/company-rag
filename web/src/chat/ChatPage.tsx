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
    <div className="min-h-screen flex flex-col bg-slate-50">
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-3">
        <h1 className="text-lg font-semibold text-slate-800">Company RAG</h1>
        <div className="flex items-center gap-3 text-sm text-slate-600">
          <span>{user?.user_id ?? ""}</span>
          <button
            onClick={handleLogout}
            className="text-slate-500 hover:text-slate-800"
          >
            로그아웃
          </button>
        </div>
      </header>
      <main className="flex-1 overflow-y-auto p-4">
        <MessageList messages={messages} />
        {pending && (
          <p className="text-sm text-slate-400 mt-3">답변 생성 중…</p>
        )}
        {error && <p className="text-sm text-red-600 mt-3">{error}</p>}
      </main>
      <MessageInput onSend={send} disabled={pending} />
    </div>
  );
}
