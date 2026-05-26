import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { ChatPage } from "./ChatPage";
import { getSessionMessages } from "../api/client";

const mockUseAuth = vi.fn();

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock("../api/client", () => ({
  getSessions: vi.fn().mockResolvedValue([]),
  getSessionMessages: vi.fn(),
  deleteSession: vi.fn(),
  setOnUnauthorized: vi.fn(),
  streamChat: vi.fn().mockReturnValue((async function* () {})()),
}));

describe("ChatPage 세션 복원", () => {
  afterEach(() => {
    localStorage.clear();
    vi.mocked(getSessionMessages).mockReset();
  });

  beforeEach(() => {
    mockUseAuth.mockReturnValue({
      user: {
        user_id: "user-alice",
        roles: ["user"],
        teams: [],
        allowed_doc_ids: [],
      },
      logout: vi.fn(),
    });
  });

  it("localStorage에 세션ID가 있으면 마운트 시 메시지 히스토리를 불러온다", async () => {
    vi.mocked(getSessionMessages).mockResolvedValue([
      { role: "user", content: "이전 질문", sources: [] },
      { role: "assistant", content: "이전 답변", sources: [] },
    ]);
    localStorage.setItem("session_id", "saved-session-123");

    render(<ChatPage />);

    await waitFor(() => {
      expect(getSessionMessages).toHaveBeenCalledWith("saved-session-123");
    });
    expect(await screen.findByText("이전 질문")).toBeInTheDocument();
    expect(screen.getByText("이전 답변")).toBeInTheDocument();
  });

  it("localStorage에 세션ID가 없으면 마운트 시 메시지를 불러오지 않는다", () => {
    render(<ChatPage />);
    expect(getSessionMessages).not.toHaveBeenCalled();
  });
});

describe("ChatPage 헤더 배지", () => {
  beforeEach(() => {
    mockUseAuth.mockReturnValue({
      user: {
        user_id: "user-alice",
        roles: ["user"],
        teams: ["general"],
        allowed_doc_ids: [],
      },
      logout: vi.fn(),
    });
  });

  it("역할 배지를 렌더링한다", () => {
    render(<ChatPage />);
    expect(screen.getByText("user")).toBeInTheDocument();
  });

  it("팀 배지를 렌더링한다", () => {
    render(<ChatPage />);
    expect(screen.getByText("general")).toBeInTheDocument();
  });

  it("teams가 비어 있으면 team: 레이블을 렌더링하지 않는다", () => {
    mockUseAuth.mockReturnValue({
      user: {
        user_id: "user-admin",
        roles: ["admin"],
        teams: [],
        allowed_doc_ids: [],
      },
      logout: vi.fn(),
    });
    render(<ChatPage />);
    expect(screen.queryByText(/^team:$/)).not.toBeInTheDocument();
  });
});
