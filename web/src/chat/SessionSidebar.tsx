import type { Session } from "../types";

interface SessionSidebarProps {
  isOpen: boolean;
  sessions: Session[];
  activeSessionId: string | null;
  onNew: () => void;
  onSelect: (sessionId: string) => void;
  onDelete: (sessionId: string) => void;
}

type DateGroup = "오늘" | "어제" | "이번 주" | "더 이전";

const DATE_GROUP_ORDER: DateGroup[] = ["오늘", "어제", "이번 주", "더 이전"];

function getDateGroup(isoDate: string): DateGroup {
  const diffMs = Date.now() - new Date(isoDate).getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  if (diffDays === 0) return "오늘";
  if (diffDays === 1) return "어제";
  if (diffDays <= 7) return "이번 주";
  return "더 이전";
}

function groupSessionsByDate(sessions: Session[]): Record<DateGroup, Session[]> {
  const groups: Record<DateGroup, Session[]> = {
    오늘: [],
    어제: [],
    "이번 주": [],
    "더 이전": [],
  };
  for (const s of sessions) {
    groups[getDateGroup(s.created_at)].push(s);
  }
  return groups;
}

export function SessionSidebar({
  isOpen,
  sessions,
  activeSessionId,
  onNew,
  onSelect,
  onDelete,
}: SessionSidebarProps) {
  const groups = groupSessionsByDate(sessions);

  return (
    <aside
      className="flex flex-col bg-canvas border-r border-hairline flex-shrink-0 overflow-hidden transition-[width] duration-200"
      style={{ width: isOpen ? 200 : 0 }}
    >
      <div className="p-2.5 pb-1.5 flex-shrink-0">
        <button
          onClick={onNew}
          className="w-full bg-primary text-white rounded-pill py-1.5 text-[12px] font-normal"
        >
          + 새 대화
        </button>
      </div>
      <nav className="flex-1 overflow-y-auto px-1.5 py-1">
        {DATE_GROUP_ORDER.map((group) => {
          const items = groups[group];
          if (items.length === 0) return null;
          return (
            <div key={group}>
              <p className="text-[9px] font-semibold text-ink-mute uppercase tracking-[0.4px] px-1.5 pt-2 pb-1">
                {group}
              </p>
              {items.map((session) => (
                <SessionItem
                  key={session.thread_id}
                  session={session}
                  isActive={session.thread_id === activeSessionId}
                  onSelect={onSelect}
                  onDelete={onDelete}
                />
              ))}
            </div>
          );
        })}
      </nav>
    </aside>
  );
}

function SessionItem({
  session,
  isActive,
  onSelect,
  onDelete,
}: {
  session: Session;
  isActive: boolean;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  return (
    <div
      className={`group flex items-center justify-between rounded-md px-2 py-1.5 mb-0.5 cursor-pointer ${
        isActive ? "bg-[#f0efff]" : "hover:bg-canvas-soft"
      }`}
      onClick={() => onSelect(session.thread_id)}
    >
      <span
        className={`text-[11px] truncate flex-1 ${
          isActive ? "text-primary font-medium" : "text-ink-mute"
        }`}
      >
        {session.title}
      </span>
      <button
        className="opacity-0 group-hover:opacity-100 text-ink-mute hover:text-ruby ml-1 text-[11px] flex-shrink-0 bg-transparent border-none cursor-pointer"
        onClick={(e) => {
          e.stopPropagation();
          onDelete(session.thread_id);
        }}
        aria-label="세션 삭제"
      >
        🗑
      </button>
    </div>
  );
}
