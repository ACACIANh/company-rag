import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ChatPage } from "./ChatPage";

const mockUseAuth = vi.fn();

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock("../api/client", () => ({
  apiFetch: vi.fn(),
  getSessions: vi.fn().mockResolvedValue([]),
  getSessionMessages: vi.fn(),
  deleteSession: vi.fn(),
  setOnUnauthorized: vi.fn(),
}));

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
