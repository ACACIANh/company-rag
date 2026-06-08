import type { Page } from "playwright";

const OVERLAY_ID = "demo-caption-overlay";

/** 화면 하단에 캡션 띠를 fade-in으로 표시(이미 있으면 텍스트만 교체). */
export async function showCaption(page: Page, text: string): Promise<void> {
  await page.evaluate(
    ({ id, text }) => {
      let el = document.getElementById(id);
      if (!el) {
        el = document.createElement("div");
        el.id = id;
        Object.assign(el.style, {
          position: "fixed",
          left: "0",
          right: "0",
          bottom: "0",
          padding: "18px 28px",
          background: "rgba(17,17,17,0.82)",
          color: "#fff",
          font: "600 18px/1.4 system-ui, sans-serif",
          textAlign: "center",
          zIndex: "2147483647",
          opacity: "0",
          transition: "opacity 0.4s ease",
          pointerEvents: "none",
        } as CSSStyleDeclaration);
        document.body.appendChild(el);
      }
      el.textContent = text;
      // 강제 reflow 후 fade-in
      void el.offsetHeight;
      el.style.opacity = "1";
    },
    { id: OVERLAY_ID, text },
  );
}

/** 캡션을 fade-out으로 감춤. */
export async function hideCaption(page: Page): Promise<void> {
  await page.evaluate((id) => {
    const el = document.getElementById(id);
    if (el) el.style.opacity = "0";
  }, OVERLAY_ID);
  await page.waitForTimeout(400);
}
