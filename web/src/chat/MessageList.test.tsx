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
    render(<MessageList messages={[interruptMsg]} onCancel={vi.fn()} pending={false} />);
    expect(screen.getByText(/manage_permission/)).toBeInTheDocument();
    expect(
      screen.getByText(/grant user:alice member department:finance/)
    ).toBeInTheDocument();
  });

  it("사유 입력 안내를 렌더한다", () => {
    render(<MessageList messages={[interruptMsg]} onCancel={vi.fn()} pending={false} />);
    expect(screen.getByText(/사유를 입력/)).toBeInTheDocument();
  });

  it("취소 버튼 클릭 시 onCancel을 호출한다", () => {
    const onCancel = vi.fn();
    render(<MessageList messages={[interruptMsg]} onCancel={onCancel} pending={false} />);
    fireEvent.click(screen.getByRole("button", { name: "취소" }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("interrupt가 없는 일반 assistant 메시지는 카드를 렌더하지 않는다", () => {
    render(
      <MessageList
        messages={[{ role: "assistant", content: "일반 답변", sources: [] }]}
        onCancel={vi.fn()}
        pending={false}
      />
    );
    expect(screen.queryByText(/사유를 입력/)).not.toBeInTheDocument();
  });

  it("pending이면 취소 버튼이 비활성화된다", () => {
    render(<MessageList messages={[interruptMsg]} onCancel={vi.fn()} pending />);
    expect(screen.getByRole("button", { name: "취소" })).toBeDisabled();
  });

  it("pending이 아니면 취소 버튼이 활성화된다", () => {
    render(<MessageList messages={[interruptMsg]} onCancel={vi.fn()} pending={false} />);
    expect(screen.getByRole("button", { name: "취소" })).toBeEnabled();
  });
});
