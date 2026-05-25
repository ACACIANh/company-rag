import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { SessionSidebar } from "./SessionSidebar";
import type { Session } from "../types";

const TODAY = new Date().toISOString();
const YESTERDAY = new Date(Date.now() - 86400000).toISOString();

const sessions: Session[] = [
  { thread_id: "t1", title: "오늘의 질문", created_at: TODAY },
  { thread_id: "t2", title: "어제의 질문", created_at: YESTERDAY },
];

describe("SessionSidebar", () => {
  it("열린 상태에서 세션 목록을 렌더링한다", () => {
    render(
      <SessionSidebar
        isOpen={true}
        sessions={sessions}
        activeSessionId={null}
        onNew={vi.fn()}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
      />
    );
    expect(screen.getByText("오늘의 질문")).toBeInTheDocument();
    expect(screen.getByText("어제의 질문")).toBeInTheDocument();
  });

  it("닫힌 상태에서 너비가 0이다", () => {
    const { container } = render(
      <SessionSidebar
        isOpen={false}
        sessions={sessions}
        activeSessionId={null}
        onNew={vi.fn()}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
      />
    );
    const aside = container.querySelector("aside")!;
    expect(aside.style.width).toBe("0px");
  });

  it("세션 클릭 시 onSelect가 thread_id로 호출된다", () => {
    const onSelect = vi.fn();
    render(
      <SessionSidebar
        isOpen={true}
        sessions={sessions}
        activeSessionId={null}
        onNew={vi.fn()}
        onSelect={onSelect}
        onDelete={vi.fn()}
      />
    );
    fireEvent.click(screen.getByText("오늘의 질문"));
    expect(onSelect).toHaveBeenCalledWith("t1");
  });

  it("새 대화 버튼 클릭 시 onNew가 호출된다", () => {
    const onNew = vi.fn();
    render(
      <SessionSidebar
        isOpen={true}
        sessions={[]}
        activeSessionId={null}
        onNew={onNew}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
      />
    );
    fireEvent.click(screen.getByText("+ 새 대화"));
    expect(onNew).toHaveBeenCalled();
  });

  it("날짜 그룹 레이블이 렌더링된다", () => {
    render(
      <SessionSidebar
        isOpen={true}
        sessions={sessions}
        activeSessionId={null}
        onNew={vi.fn()}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
      />
    );
    expect(screen.getByText("오늘")).toBeInTheDocument();
    expect(screen.getByText("어제")).toBeInTheDocument();
  });
});
