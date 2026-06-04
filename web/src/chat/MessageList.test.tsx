import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { MessageList } from "./MessageList";
import type { ChatMessage } from "../types";

describe("MessageList interrupt 카드", () => {
  const interruptMsg: ChatMessage = {
    role: "assistant",
    content: "",
    interrupt: [
      { tool: "manage_permission", planned_action: "grant user:alice member department:finance" },
    ],
  };

  it("계획된 동작(tool·planned_action)을 렌더한다", () => {
    render(<MessageList messages={[interruptMsg]} onCancel={vi.fn()} pending={false} awaitingJustification={true} />);
    expect(screen.getByText(/manage_permission/)).toBeInTheDocument();
    expect(
      screen.getByText(/grant user:alice member department:finance/)
    ).toBeInTheDocument();
  });

  it("사유 입력 안내를 렌더한다", () => {
    render(<MessageList messages={[interruptMsg]} onCancel={vi.fn()} pending={false} awaitingJustification={true} />);
    expect(screen.getByText(/사유를 입력/)).toBeInTheDocument();
  });

  it("취소 버튼 클릭 시 onCancel을 호출한다", () => {
    const onCancel = vi.fn();
    render(<MessageList messages={[interruptMsg]} onCancel={onCancel} pending={false} awaitingJustification={true} />);
    fireEvent.click(screen.getByRole("button", { name: "취소" }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("interrupt가 없는 일반 assistant 메시지는 카드를 렌더하지 않는다", () => {
    render(
      <MessageList
        messages={[{ role: "assistant", content: "일반 답변", sources: [] }]}
        onCancel={vi.fn()}
        pending={false}
        awaitingJustification={false}
      />
    );
    expect(screen.queryByText(/사유를 입력/)).not.toBeInTheDocument();
  });

  it("pending이면 취소 버튼이 비활성화된다", () => {
    render(<MessageList messages={[interruptMsg]} onCancel={vi.fn()} pending awaitingJustification={true} />);
    expect(screen.getByRole("button", { name: "취소" })).toBeDisabled();
  });

  it("awaitingJustification이 true이고 pending이 아니면 취소 버튼이 활성화된다", () => {
    render(<MessageList messages={[interruptMsg]} onCancel={vi.fn()} pending={false} awaitingJustification={true} />);
    expect(screen.getByRole("button", { name: "취소" })).toBeEnabled();
  });

  it("awaitingJustification이 false이면 진행 후 취소 버튼이 비활성화된다", () => {
    render(<MessageList messages={[interruptMsg]} onCancel={vi.fn()} pending={false} awaitingJustification={false} />);
    expect(screen.getByRole("button", { name: "취소" })).toBeDisabled();
  });
});

describe("MessageList clarify 카드", () => {
  const clarifyMsg: ChatMessage = {
    role: "assistant",
    content: "",
    clarify: {
      message: '"연차 어떻게 해?" — 어떤 방식으로 처리할까요?',
      options: ["사내 문서에서 찾기", "업무 DB 조회 / 권한 도구 사용"],
    },
  };

  it("메시지와 선택지 버튼 두 개를 렌더한다", () => {
    render(
      <MessageList
        messages={[clarifyMsg]}
        onCancel={vi.fn()}
        pending={false}
        awaitingJustification={false}
        onClarifySelect={vi.fn()}
        awaitingClarify={true}
      />
    );
    expect(screen.getByText(/어떤 방식으로 처리할까요/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "사내 문서에서 찾기" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "업무 DB 조회 / 권한 도구 사용" })).toBeInTheDocument();
  });

  it("버튼 클릭 시 onClarifySelect를 레이블과 함께 호출한다", () => {
    const onClarifySelect = vi.fn();
    render(
      <MessageList
        messages={[clarifyMsg]}
        onCancel={vi.fn()}
        pending={false}
        awaitingJustification={false}
        onClarifySelect={onClarifySelect}
        awaitingClarify={true}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: "사내 문서에서 찾기" }));
    expect(onClarifySelect).toHaveBeenCalledWith("사내 문서에서 찾기");
  });

  it("awaitingClarify=false이면 버튼이 비활성화된다", () => {
    render(
      <MessageList
        messages={[clarifyMsg]}
        onCancel={vi.fn()}
        pending={false}
        awaitingJustification={false}
        onClarifySelect={vi.fn()}
        awaitingClarify={false}
      />
    );
    expect(screen.getByRole("button", { name: "사내 문서에서 찾기" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "업무 DB 조회 / 권한 도구 사용" })).toBeDisabled();
  });
});
