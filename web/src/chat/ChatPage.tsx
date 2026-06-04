import { useEffect, useRef, useState } from "react";
import { getSessions, getSessionMessages, deleteSession, streamChat } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { ApiError } from "../types";
import type { ChatMessage, Session } from "../types";
import { MessageInput, type MessageInputHandle } from "./MessageInput";
import { MessageList } from "./MessageList";
import { SessionSidebar } from "./SessionSidebar";

export function ChatPage() {
  const { user, logout } = useAuth();
  const [sessionId, setSessionId] = useState<string | null>(() =>
    localStorage.getItem("session_id")
  );
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pending, setPending] = useState(false);
  const [awaitingJustification, setAwaitingJustification] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const selectingSessionRef = useRef<string | null>(null);
  const scrollRef = useRef<HTMLElement>(null);
  const isNearBottomRef = useRef(true);
  const inputRef = useRef<MessageInputHandle>(null);

  const handleScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    isNearBottomRef.current = el.scrollTop + el.clientHeight >= el.scrollHeight - 50;
  };

  useEffect(() => {
    if (!isNearBottomRef.current) return;
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  useEffect(() => {
    if (sessionId) localStorage.setItem("session_id", sessionId);
  }, [sessionId]);

  useEffect(() => {
    inputRef.current?.focus();
  }, [sessionId]);

  useEffect(() => {
    getSessions().then(setSessions).catch(() => {});
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/exhaustive-deps
    const id = localStorage.getItem("session_id");
    if (!id) return;
    setLoadingHistory(true);
    getSessionMessages(id)
      .then((history) =>
        setMessages(
          history.map((m) => ({ role: m.role, content: m.content, sources: m.sources }))
        )
      )
      .catch(() => {
        setSessionId(null);
        localStorage.removeItem("session_id");
      })
      .finally(() => setLoadingHistory(false));
  }, []); // mount only: sessionId 초기값(localStorage)으로 히스토리 복원

  const send = async (question: string) => {
    isNearBottomRef.current = true;
    const isNewSession = sessionId === null;
    setAwaitingJustification(false);
    setError(null);
    setPending(true);
    if (question !== "") {
      setMessages((prev) => [...prev, { role: "user", content: question }]);
    }

    let assistantAdded = false;

    try {
      for await (const event of streamChat(question, sessionId)) {
        if (event.type === "token") {
          if (!assistantAdded) {
            setMessages((prev) => [
              ...prev,
              { role: "assistant", content: event.content, sources: [], streaming: true },
            ]);
            assistantAdded = true;
          } else {
            setMessages((prev) => {
              const next = [...prev];
              const last = next[next.length - 1];
              next[next.length - 1] = { ...last, content: last.content + event.content };
              return next;
            });
          }
        } else if (event.type === "sources") {
          if (assistantAdded) {
            setMessages((prev) => {
              const next = [...prev];
              next[next.length - 1] = { ...next[next.length - 1], sources: event.sources, route: event.route };
              return next;
            });
          }
        } else if (event.type === "done") {
          if (assistantAdded) {
            setMessages((prev) => {
              const next = [...prev];
              next[next.length - 1] = { ...next[next.length - 1], streaming: false };
              return next;
            });
          }
          setSessionId(event.session_id);
          if (isNewSession) {
            getSessions().then(setSessions).catch(() => {});
          }
        } else if (event.type === "interrupt") {
          setMessages((prev) => [
            ...prev,
            { role: "assistant", content: "", interrupt: event.actions },
          ]);
          setAwaitingJustification(true);
        } else if (event.type === "error") {
          setError(event.message);
        }
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
      setAwaitingJustification(false);
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
    setAwaitingJustification(false);
    localStorage.removeItem("session_id");
  };

  const handleDeleteSession = async (id: string) => {
    setSessions((prev) => prev.filter((s) => s.thread_id !== id));
    if (id === sessionId) {
      setSessionId(null);
      setMessages([]);
      setAwaitingJustification(false);
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
            <span className="text-[14px] font-light text-ink-mute ml-1"> Organization Assistant</span>
          </h1>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[13px] text-ink-mute font-normal tracking-[-0.39px]">
              {user?.user_id ?? ""}
            </span>
            {user && (
              <>
                <span className="text-[11px] text-ink-mute">role:</span>
                {user.roles.map((r) => (
                  <span
                    key={r}
                    className="bg-primary-muted text-primary-deep text-[10px] font-[400] tracking-[0.1px] rounded-pill px-2 py-[3px] uppercase"
                  >
                    {r}
                  </span>
                ))}
                {user.departments.length > 0 && (
                  <>
                    <span className="text-[11px] text-ink-mute">부서:</span>
                    {user.departments.map((d) => (
                      <span
                        key={d}
                        className="bg-primary-muted text-primary-deep text-[10px] font-[400] tracking-[0.1px] rounded-pill px-2 py-[3px] uppercase"
                      >
                        {d}
                      </span>
                    ))}
                  </>
                )}
              </>
            )}
          </div>
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
          <main ref={scrollRef} onScroll={handleScroll} className="flex-1 overflow-y-auto px-4 py-6 max-w-3xl w-full mx-auto">
            {loadingHistory ? (
              <p className="text-[13px] text-ink-mute text-center mt-8">
                대화 기록을 불러오는 중…
              </p>
            ) : (
              <MessageList messages={messages} onCancel={() => send("")} pending={pending} />
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
            <MessageInput
              ref={inputRef}
              onSend={send}
              disabled={pending || loadingHistory}
              awaitingJustification={awaitingJustification}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
