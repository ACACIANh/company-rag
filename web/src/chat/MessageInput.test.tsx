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
});
