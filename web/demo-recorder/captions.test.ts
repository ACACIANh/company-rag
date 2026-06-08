import { describe, it, expect } from "vitest";
import { captionFor } from "./captions";
import type { Scene } from "./lib/types";

const base: Scene = {
  id: "04", account: "daesu", password: "x",
  display_name: "오대수", dept: "인사",
  question: "보안 관련해서 알려줘", kind: "clarify", resume_text: "사내 문서 검색 (RAG)",
};

describe("captionFor", () => {
  it("includes id, name(dept), and kind description", () => {
    expect(captionFor(base)).toBe("장면 04 · 오대수(인사) · 모호한 질문 → 재질문(HITL)");
  });

  it("omits dept parentheses when dept is null", () => {
    const admin: Scene = { ...base, id: "08", display_name: "이우진", dept: null, kind: "sql_read" };
    expect(captionFor(admin)).toBe("장면 08 · 이우진 · SQL 조회 — 실행 사유 승인(HITL)");
  });

  it("supports per-id override", () => {
    const after: Scene = { ...base, id: "15", account: "mido", display_name: "미도", dept: "제품", kind: "permission" };
    expect(captionFor(after)).toBe("장면 15 · 미도(제품) · 부서 위임 후 — 권한 재확인");
  });
});
