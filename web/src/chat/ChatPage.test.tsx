import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { ChatPage } from "./ChatPage";
import { getSessions, getSessionMessages, streamChat } from "../api/client";

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
        departments: [],
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
        departments: ["general"],
      },
      logout: vi.fn(),
    });
  });

  it("역할 배지를 렌더링한다", () => {
    render(<ChatPage />);
    expect(screen.getByText("user")).toBeInTheDocument();
  });

  it("부서 배지를 렌더링한다", () => {
    render(<ChatPage />);
    expect(screen.getByText("general")).toBeInTheDocument();
  });

  it("departments가 비어 있으면 부서: 레이블을 렌더링하지 않는다", () => {
    mockUseAuth.mockReturnValue({
      user: {
        user_id: "user-admin",
        roles: ["admin"],
        departments: [],
      },
      logout: vi.fn(),
    });
    render(<ChatPage />);
    expect(screen.queryByText(/^부서:$/)).not.toBeInTheDocument();
  });
});

describe("ChatPage interrupt(JUSTIFY) 흐름", () => {
  beforeEach(() => {
    mockUseAuth.mockReturnValue({
      user: { user_id: "user-admin", roles: ["admin"], departments: [] },
      logout: vi.fn(),
    });
    vi.mocked(streamChat).mockReset();
    vi.mocked(getSessions).mockResolvedValue([]);
  });

  afterEach(() => {
    localStorage.clear();
  });

  it("interrupt 이벤트 수신 시 안내 카드를 렌더하고 사유 입력 모드로 전환한다", async () => {
    vi.mocked(streamChat).mockReturnValue(
      (async function* () {
        yield {
          type: "interrupt",
          actions: [
            { tool: "manage_permission", planned_action: "grant user:alice member department:finance" },
          ],
        };
        yield { type: "done", session_id: "s-1" };
      })()
    );

    render(<ChatPage />);
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "alice를 finance에 추가해줘" },
    });
    fireEvent.click(screen.getByRole("button", { name: "전송" }));

    expect(
      await screen.findByText(/grant user:alice member department:finance/)
    ).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText("실행 사유를 입력하세요")
    ).toBeInTheDocument();
  });

  it("사유를 전송하면 streamChat을 다시 호출하고 사유 입력 모드를 해제한다", async () => {
    vi.mocked(streamChat)
      .mockReturnValueOnce(
        (async function* () {
          yield {
            type: "interrupt",
            actions: [{ tool: "manage_permission", planned_action: "grant ..." }],
          };
          yield { type: "done", session_id: "s-1" };
        })()
      )
      .mockReturnValueOnce(
        (async function* () {
          yield { type: "token", content: "실행했습니다" };
          yield { type: "done", session_id: "s-1" };
        })()
      );

    render(<ChatPage />);
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "alice를 finance에 추가해줘" },
    });
    fireEvent.click(screen.getByRole("button", { name: "전송" }));
    await screen.findByText(/grant/);

    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "감사 대응을 위해 필요합니다" },
    });
    fireEvent.click(screen.getByRole("button", { name: "전송" }));

    await waitFor(() => expect(streamChat).toHaveBeenCalledTimes(2));
    expect(streamChat).toHaveBeenLastCalledWith(
      "감사 대응을 위해 필요합니다",
      "s-1"
    );
    await waitFor(() =>
      expect(
        screen.getByPlaceholderText(/질문을 입력하세요/)
      ).toBeInTheDocument()
    );
  });

  it("취소 버튼은 빈 사유로 streamChat을 호출한다", async () => {
    vi.mocked(streamChat)
      .mockReturnValueOnce(
        (async function* () {
          yield {
            type: "interrupt",
            actions: [{ tool: "manage_permission", planned_action: "grant ..." }],
          };
          yield { type: "done", session_id: "s-1" };
        })()
      )
      .mockReturnValueOnce((async function* () {})());

    render(<ChatPage />);
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "alice를 finance에 추가해줘" },
    });
    fireEvent.click(screen.getByRole("button", { name: "전송" }));
    await screen.findByText(/grant/);

    fireEvent.click(screen.getByRole("button", { name: "취소" }));

    await waitFor(() => expect(streamChat).toHaveBeenCalledTimes(2));
    expect(streamChat).toHaveBeenLastCalledWith("", "s-1");
  });

  it("interrupt 대기 중 다른 세션으로 전환하면 사유 입력 모드가 해제된다", async () => {
    vi.mocked(getSessions).mockResolvedValue([
      { thread_id: "s-other", title: "다른 세션", created_at: "2026-06-03T00:00:00Z" },
    ]);
    vi.mocked(getSessionMessages).mockResolvedValue([
      { role: "user", content: "다른 질문", sources: [] },
    ]);
    vi.mocked(streamChat).mockReturnValue(
      (async function* () {
        yield { type: "interrupt", actions: [{ tool: "manage_permission", planned_action: "grant ..." }] };
        yield { type: "done", session_id: "s-1" };
      })()
    );

    render(<ChatPage />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "alice 추가" } });
    fireEvent.click(screen.getByRole("button", { name: "전송" }));
    await screen.findByPlaceholderText("실행 사유를 입력하세요");

    // 사이드바에서 다른 세션 선택
    fireEvent.click(await screen.findByText("다른 세션"));

    await waitFor(() =>
      expect(screen.getByPlaceholderText(/질문을 입력하세요/)).toBeInTheDocument()
    );
  });
});

describe("ChatPage clarify 흐름", () => {
  beforeEach(() => {
    mockUseAuth.mockReturnValue({
      user: { user_id: "user-admin", roles: ["admin"], departments: [] },
      logout: vi.fn(),
    });
    vi.mocked(streamChat).mockReset();
    vi.mocked(getSessions).mockResolvedValue([]);
  });

  afterEach(() => {
    localStorage.clear();
  });

  it("clarify 이벤트 수신 시 선택지 버튼을 렌더한다", async () => {
    vi.mocked(streamChat).mockReturnValue(
      (async function* () {
        yield {
          type: "clarify",
          message: '"연차 어떻게 해?" — 어떤 방식으로 처리할까요?',
          options: ["사내 문서에서 찾기", "업무 DB 조회 / 권한 도구 사용"],
        };
        yield { type: "done", session_id: "s-1" };
      })()
    );

    render(<ChatPage />);
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "연차 어떻게 해?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "전송" }));

    expect(
      await screen.findByRole("button", { name: "사내 문서에서 찾기" })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "업무 DB 조회 / 권한 도구 사용" })
    ).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText("위에서 방식을 선택해주세요")
    ).toBeInTheDocument();
  });

  it("선택지 버튼 클릭 시 streamChat을 해당 레이블로 호출한다", async () => {
    vi.mocked(streamChat)
      .mockReturnValueOnce(
        (async function* () {
          yield {
            type: "clarify",
            message: '"연차 어떻게 해?" — 어떤 방식으로 처리할까요?',
            options: ["사내 문서에서 찾기", "업무 DB 조회 / 권한 도구 사용"],
          };
          yield { type: "done", session_id: "s-1" };
        })()
      )
      .mockReturnValueOnce(
        (async function* () {
          yield { type: "token", content: "연차 정책은..." };
          yield { type: "done", session_id: "s-1" };
        })()
      );

    render(<ChatPage />);
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "연차 어떻게 해?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "전송" }));

    const docBtn = await screen.findByRole("button", { name: "사내 문서에서 찾기" });
    fireEvent.click(docBtn);

    await waitFor(() => expect(streamChat).toHaveBeenCalledTimes(2));
    expect(streamChat).toHaveBeenLastCalledWith("사내 문서에서 찾기", "s-1");
    await waitFor(() =>
      expect(
        screen.getByPlaceholderText(/질문을 입력하세요/)
      ).toBeInTheDocument()
    );
  });

  it("clarify 대기 중 세션 전환 시 awaitingClarify가 해제된다", async () => {
    vi.mocked(getSessions).mockResolvedValue([
      { thread_id: "s-other", title: "다른 세션", created_at: "2026-06-03T00:00:00Z" },
    ]);
    vi.mocked(getSessionMessages).mockResolvedValue([
      { role: "user", content: "다른 질문", sources: [] },
    ]);
    vi.mocked(streamChat).mockReturnValue(
      (async function* () {
        yield {
          type: "clarify",
          message: '"연차?" — 방식을 선택하세요.',
          options: ["사내 문서에서 찾기", "업무 DB 조회 / 권한 도구 사용"],
        };
        yield { type: "done", session_id: "s-1" };
      })()
    );

    render(<ChatPage />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "연차?" } });
    fireEvent.click(screen.getByRole("button", { name: "전송" }));
    await screen.findByRole("button", { name: "사내 문서에서 찾기" });

    fireEvent.click(await screen.findByText("다른 세션"));

    await waitFor(() =>
      expect(screen.getByPlaceholderText(/질문을 입력하세요/)).toBeInTheDocument()
    );
  });
});
