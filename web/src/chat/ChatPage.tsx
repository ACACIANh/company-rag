import { useEffect, useRef, useState } from "react";
import { apiFetch, getSessions, getSessionMessages, deleteSession } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { ApiError } from "../types";
import type { ChatMessage, ChatResponse, Session } from "../types";
import { MessageInput } from "./MessageInput";
import { MessageList } from "./MessageList";
import { SessionSidebar } from "./SessionSidebar";

export function ChatPage() {
  const { user, logout } = useAuth();
  const [sessionId, setSessionId] = useState<string | null>(() =>
    localStorage.getItem("session_id")
  );
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const selectingSessionRef = useRef<string | null>(null);

  useEffect(() => {
    if (sessionId) localStorage.setItem("session_id", sessionId);
  }, [sessionId]);

  useEffect(() => {
    getSessions().then(setSessions).catch(() => {});
  }, []);

  const send = async (question: string) => {
    const isNewSession = sessionId === null;
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
      if (isNewSession) {
        getSessions().then(setSessions).catch(() => {});
      }
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

  const handleSelectSession = async (id: string) => {
    if (id === sessionId) return;
    selectingSessionRef.current = id;
    setLoadingHistory(true);
    setError(null);
    try {
      const history = await getSessionMessages(id);
      if (selectingSessionRef.current !== id) return;
      setMessages(
        history.map((m) => ({
          role: m.role,
          content: m.content,
          sources: m.sources,
        }))
      );
      setSessionId(id);
      localStorage.setItem("session_id", id);
    } catch {
      if (selectingSessionRef.current === id) {
        setError("세션을 불러오는 중 오류가 발생했습니다.");
      }
    } finally {
      if (selectingSessionRef.current === id) {
        setLoadingHistory(false);
      }
    }
  };

  const handleNewSession = () => {
    setSessionId(null);
    setMessages([]);
    setError(null);
    localStorage.removeItem("session_id");
  };

  const handleDeleteSession = async (id: string) => {
    setSessions((prev) => prev.filter((s) => s.thread_id !== id));
    if (id === sessionId) {
      setSessionId(null);
      setMessages([]);
      localStorage.removeItem("session_id");
    }
    try {
      await deleteSession(id);
    } catch {
      getSessions().then(setSessions).catch(() => {});
    }
  };

  const handleLogout = () => {
    setMessages([]);
    setSessionId(null);
    localStorage.removeItem("session_id");
    logout();
  };

  return (
    <div className="h-screen flex flex-col bg-canvas-soft overflow-hidden">
      <header
        className="flex items-center justify-between border-b border-hairline bg-canvas px-6 py-3 flex-shrink-0"
        style={{ boxShadow: "rgba(0,55,112,0.08) 0 1px 3px" }}
      >
        <div className="flex items-center gap-3">
          <button
            onClick={() => setSidebarOpen((o) => !o)}
            className="flex flex-col gap-[4px] p-1 text-ink-mute hover:text-ink transition-colors"
            aria-label="사이드바 토글"
          >
            <span className="block w-4 h-[1.5px] bg-current rounded" />
            <span className="block w-4 h-[1.5px] bg-current rounded" />
            <span className="block w-4 h-[1.5px] bg-current rounded" />
          </button>
          <h1
            className="text-[20px] font-light text-ink tracking-[-0.2px]"
            style={{ fontFeatureSettings: '"ss01"' }}
          >
            Friday
            <span className="text-[14px] font-light text-ink-mute ml-1">, Organization Assistant</span>
          </h1>
        </div>
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

      <div className="flex flex-1 overflow-hidden">
        <SessionSidebar
          isOpen={sidebarOpen}
          sessions={sessions}
          activeSessionId={sessionId}
          onNew={handleNewSession}
          onSelect={handleSelectSession}
          onDelete={handleDeleteSession}
        />

        <div className="flex flex-col flex-1 overflow-hidden">
          <main className="flex-1 overflow-y-auto px-4 py-6 max-w-3xl w-full mx-auto">
            {loadingHistory ? (
              <p className="text-[13px] text-ink-mute text-center mt-8">
                대화 기록을 불러오는 중…
              </p>
            ) : (
              <MessageList messages={messages} />
            )}
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
                <span className="text-[13px] text-ink-mute font-normal">
                  답변 생성 중…
                </span>
              </div>
            )}
            {error && (
              <p className="text-[13px] text-ruby font-normal mt-3">{error}</p>
            )}
          </main>

          <div className="max-w-3xl w-full mx-auto px-4 pb-4 flex-shrink-0">
            <MessageInput onSend={send} disabled={pending || loadingHistory} />
          </div>
        </div>
      </div>
    </div>
  );
}
