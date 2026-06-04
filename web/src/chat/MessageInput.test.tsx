import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { MessageInput } from "./MessageInput";

describe("MessageInput placeholder", () => {
  it("기본 placeholder는 질문 안내를 보여준다", () => {
    render(<MessageInput onSend={vi.fn()} disabled={false} />);
    expect(
      screen.getByPlaceholderText(/질문을 입력하세요/)
    ).toBeInTheDocument();
  });

  it("awaitingJustification이면 사유 입력 placeholder로 바뀐다", () => {
    render(
      <MessageInput onSend={vi.fn()} disabled={false} awaitingJustification />
    );
    expect(
      screen.getByPlaceholderText("실행 사유를 입력하세요")
    ).toBeInTheDocument();
  });

  it("awaitingClarify이면 선택 안내 placeholder로 바뀐다", () => {
    render(
      <MessageInput onSend={vi.fn()} disabled={false} awaitingClarify />
    );
    expect(
      screen.getByPlaceholderText("위에서 방식을 선택해주세요")
    ).toBeInTheDocument();
  });

  it("awaitingClarify이면 textarea가 비활성화된다", () => {
    render(
      <MessageInput onSend={vi.fn()} disabled={false} awaitingClarify />
    );
    expect(screen.getByRole("textbox")).toBeDisabled();
  });
});
