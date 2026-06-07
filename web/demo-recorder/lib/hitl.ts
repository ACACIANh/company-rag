import type { Page } from "playwright";

const TYPING_DELAY_MS = 40;

/** JUSTIFY interrupt: 승인 카드가 뜰 때까지 대기 후 사유를 입력하고 전송. */
export async function submitJustification(page: Page, reason: string): Promise<void> {
  await page.getByText("실행 승인이 필요합니다").waitFor({ state: "visible", timeout: 30000 });
  const box = page.locator('textarea[placeholder="실행 사유를 입력하세요"]');
  await box.waitFor({ state: "visible", timeout: 10000 });
  await box.click();
  await box.pressSequentially(reason, { delay: TYPING_DELAY_MS });
  await page.getByRole("button", { name: "전송" }).click();
}

/** clarify: 주어진 label과 일치하는 옵션 버튼을 클릭. */
export async function selectClarifyOption(page: Page, label: string): Promise<void> {
  const option = page.getByRole("button", { name: label });
  await option.waitFor({ state: "visible", timeout: 30000 });
  await option.click();
}
