import type { Page } from "playwright";

const TYPING_DELAY_MS = 40;

/** 채팅 입력창에 질문을 타이핑하고 전송. */
export async function askQuestion(page: Page, question: string): Promise<void> {
  const box = page.locator("textarea");
  await box.click();
  await box.pressSequentially(question, { delay: TYPING_DELAY_MS });
  await page.getByRole("button", { name: "전송" }).click();
}

/**
 * 스트리밍 응답이 끝날 때까지 대기.
 * "답변 생성 중…" 텍스트가 없고 첫 textarea가 비활성(disabled)이 아닐 때 완료로 판단.
 */
export async function waitForAnswer(page: Page, timeoutMs = 60000): Promise<void> {
  await page.waitForFunction(
    () => {
      const loading = Array.from(document.querySelectorAll("*")).some(
        (n) => n.textContent?.trim() === "답변 생성 중…",
      );
      const ta = document.querySelector("textarea") as HTMLTextAreaElement | null;
      const enabled = ta != null && !ta.disabled;
      return !loading && enabled;
    },
    undefined,
    { timeout: timeoutMs, polling: 200 },
  );
}
