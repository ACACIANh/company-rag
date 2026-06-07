import type { Page } from "playwright";

const TYPING_DELAY_MS = 40;

/** baseURL의 로그인 폼에서 username/password로 로그인하고 채팅 화면 진입을 대기. */
export async function login(
  page: Page,
  baseURL: string,
  username: string,
  password: string,
): Promise<void> {
  await page.goto(baseURL);
  await page.locator('input[autocomplete="username"]').fill("");
  await page.locator('input[autocomplete="username"]').pressSequentially(username, { delay: TYPING_DELAY_MS });
  await page.locator('input[type="password"]').pressSequentially(password, { delay: TYPING_DELAY_MS });
  await page.locator('button[type="submit"]').click();
  // 채팅 화면의 질문 입력창이 나타날 때까지 대기
  await page.locator("textarea").waitFor({ state: "visible", timeout: 15000 });
}

/** 헤더의 로그아웃 버튼을 눌러 로그인 화면으로 복귀. */
export async function logout(page: Page): Promise<void> {
  await page.getByRole("button", { name: "로그아웃" }).click();
  await page.locator('input[autocomplete="username"]').waitFor({ state: "visible", timeout: 10000 });
}
