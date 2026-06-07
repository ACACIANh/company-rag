import { execFileSync } from "node:child_process";
import { readFileSync, renameSync, mkdirSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import type { Scene } from "./lib/types";
import { captionFor } from "./captions";
import { needsRelogin, interactionFor } from "./lib/flow";
import { showCaption, hideCaption } from "./lib/overlay";
import { login, logout } from "./lib/auth";
import { askQuestion, waitForAnswer } from "./lib/chat";
import { submitJustification, selectClarifyOption } from "./lib/hitl";

const HERE = dirname(fileURLToPath(import.meta.url));
const BACKEND = resolve(HERE, "../../backend");
const PY = resolve(BACKEND, ".venv/bin/python");
const SCENES_JSON = resolve(HERE, "scenes.json");
const OUT_DIR = resolve(HERE, "out");

const BASE_URL = process.env.DEMO_BASE_URL ?? "http://localhost:5173";
const READ_PAUSE_MS = 2500;
const VIEWPORT = { width: 1440, height: 900 };

function runPython(args: string[]): void {
  execFileSync(PY, args, { cwd: BACKEND, stdio: "inherit" });
}

async function main(): Promise<void> {
  // 1) SSOT 파생 + 상태 초기화 (서버는 사용자가 미리 기동)
  console.log("▶ scenes.json export");
  runPython(["-m", "scripts.demo_bench", "--export-scenes", SCENES_JSON]);
  console.log("▶ demo_reset");
  runPython(["-m", "scripts.demo_reset"]);

  const scenes: Scene[] = JSON.parse(readFileSync(SCENES_JSON, "utf-8"));
  mkdirSync(OUT_DIR, { recursive: true });

  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: VIEWPORT,
    recordVideo: { dir: OUT_DIR, size: VIEWPORT },
  });
  const page = await context.newPage();

  let prevAccount: string | null = null;
  try {
    for (const scene of scenes) {
      console.log(`▶ 장면 ${scene.id} (${scene.account}/${scene.kind})`);
      if (needsRelogin(prevAccount, scene.account)) {
        if (prevAccount !== null) await logout(page);
        await login(page, BASE_URL, scene.account, scene.password);
        prevAccount = scene.account;
      }

      await showCaption(page, captionFor(scene));
      await askQuestion(page, scene.question);

      const interaction = interactionFor(scene);
      if (interaction === "clarify") {
        await selectClarifyOption(page, scene.resume_text!);
        await waitForAnswer(page);
      } else if (interaction === "justify") {
        await waitForAnswer(page); // 승인 카드 등장까지 1차 응답 완료 대기
        await submitJustification(page, scene.resume_text!);
        await waitForAnswer(page);
      } else {
        await waitForAnswer(page);
      }

      await page.waitForTimeout(READ_PAUSE_MS);
      await hideCaption(page);
    }
  } finally {
    await context.close(); // 비디오 flush
    const video = page.video();
    const raw = await video?.path();
    await browser.close();
    if (raw) {
      const stamp = new Date().toISOString().replace(/[:.]/g, "-");
      const final = resolve(OUT_DIR, `demo-${stamp}.webm`);
      renameSync(raw, final);
      console.log(`✔ 영상 저장: ${final}`);
    }
  }
}

main().catch((err) => {
  console.error("✖ 녹화 실패:", err);
  process.exit(1);
});
