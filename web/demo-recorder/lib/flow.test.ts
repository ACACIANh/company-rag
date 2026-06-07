import { describe, it, expect } from "vitest";
import { needsRelogin, interactionFor } from "./flow";
import type { Scene } from "./types";

const scene = (over: Partial<Scene>): Scene => ({
  id: "00", account: "daesu", password: "x", display_name: "오대수", dept: "인사",
  question: "q", kind: "rag", resume_text: null, ...over,
});

describe("needsRelogin", () => {
  it("true on first scene (no previous account)", () => {
    expect(needsRelogin(null, "daesu")).toBe(true);
  });
  it("false when same account as previous", () => {
    expect(needsRelogin("daesu", "daesu")).toBe(false);
  });
  it("true when account changes", () => {
    expect(needsRelogin("daesu", "admin")).toBe(true);
  });
});

describe("interactionFor", () => {
  it("clarify when kind is clarify", () => {
    expect(interactionFor(scene({ kind: "clarify", resume_text: "사내 문서 검색 (RAG)" }))).toBe("clarify");
  });
  it("justify when resume_text present and not clarify", () => {
    expect(interactionFor(scene({ kind: "sql_read", resume_text: "사유" }))).toBe("justify");
  });
  it("plain when no resume_text", () => {
    expect(interactionFor(scene({ kind: "rag_block", resume_text: null }))).toBe("plain");
  });
  it("plain for sql_write_deny (no resume)", () => {
    expect(interactionFor(scene({ kind: "sql_write_deny", resume_text: null }))).toBe("plain");
  });
});
