import type { Page } from "playwright";

const TYPING_DELAY_MS = 40;

/**
 * 채팅 입력창에 질문을 타이핑하고 Enter로 전송.
 * Enter 제출은 전송 버튼의 enabled 레이스를 피한다. 제출이 반영되면
 * MessageInput이 textarea를 비우므로(value=""), 그것으로 제출을 확인하고
 * 실패 시 전송 버튼으로 1회 폴백한다.
 */
export async function askQuestion(page: Page, question: string): Promise<void> {
  const box = page.locator("textarea");
  await box.click();
  await box.fill("");
  await box.pressSequentially(question, { delay: TYPING_DELAY_MS });
  await page.keyboard.press("Enter");
  try {
    await page.waitForFunction(
      () => {
        const t = document.querySelector("textarea") as HTMLTextAreaElement | null;
        return t != null && t.value.trim() === "";
      },
      undefined,
      { timeout: 3000, polling: 100 },
    );
  } catch {
    const send = page.getByRole("button", { name: "전송" });
    if (await send.isEnabled().catch(() => false)) await send.click();
  }
}

/**
 * 이번 턴이 도달한 UI 상태를 감지해서 반환한다.
 * composer placeholder는 현재 awaiting* 플래그를 반영하므로(히스토리 텍스트와
 * 달리) 이번 턴의 활성 상태를 신뢰성 있게 판별할 수 있다.
 * - "방식을 선택" → clarify, "실행 사유" → interrupt(justify), "질문을 입력" + 활성 → answer
 */
export async function settleTurn(
  page: Page,
  timeoutMs = 60000,
): Promise<"clarify" | "interrupt" | "answer"> {
  const handle = await page.waitForFunction(
    () => {
      const loading = Array.from(document.querySelectorAll("*")).some(
        (n) => n.textContent?.trim() === "답변 생성 중…",
      );
      if (loading) return null;
      const ta = document.querySelector("textarea") as HTMLTextAreaElement | null;
      const ph = ta?.getAttribute("placeholder") ?? "";
      if (ph.includes("방식을 선택")) return "clarify";
      if (ph.includes("실행 사유")) return "interrupt";
      if (ph.includes("질문을 입력") && ta != null && !ta.disabled) return "answer";
      return null;
    },
    undefined,
    { timeout: timeoutMs, polling: 200 },
  );
  return (await handle.jsonValue()) as "clarify" | "interrupt" | "answer";
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
