import type { Page } from "playwright";

const TYPING_DELAY_MS = 40;
const DEFAULT_CLARIFY_OPTION = "사내 문서 검색 (RAG)";

/**
 * JUSTIFY interrupt: 사유 입력창에 사유를 입력하고 Enter로 전송.
 * 호출 전 settleTurn으로 interrupt 상태가 확인된 상태를 전제하되, 안전하게
 * 사유 입력창(placeholder)이 보일 때까지 대기한다. Enter 제출로 버튼 레이스 회피.
 */
export async function submitJustification(page: Page, reason: string): Promise<void> {
  const box = page.locator('textarea[placeholder="실행 사유를 입력하세요"]');
  await box.waitFor({ state: "visible", timeout: 30000 });
  await box.click();
  await box.fill("");
  await box.pressSequentially(reason, { delay: TYPING_DELAY_MS });
  await page.keyboard.press("Enter");
}

/**
 * clarify: 활성(가장 최근) 카드의 옵션 버튼을 클릭.
 * 같은 라벨 버튼이 히스토리에 여러 개 있을 수 있으므로 .last()로 최신 카드를
 * 고르고, click의 actionability(visible+enabled+stable)로 활성 버튼만 누른다.
 * label 미지정 시 기본 옵션으로 언블록.
 */
export async function selectClarifyOption(
  page: Page,
  label: string = DEFAULT_CLARIFY_OPTION,
): Promise<void> {
  const option = page.getByRole("button", { name: label }).last();
  await option.click({ timeout: 30000 });
}
