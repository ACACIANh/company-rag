import { describe, it, expect } from "vitest";
import { needsRelogin, interactionFor, resolveAction } from "./flow";
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

describe("resolveAction", () => {
  // 기대한 상호작용이 실제 UI 결과와 일치할 때: 정상 동작, 경고 없음
  it("clarify expected + clarify actual → clarifyOption, no warn", () => {
    expect(resolveAction("clarify", "clarify")).toEqual({ action: "clarifyOption", warn: null });
  });
  it("justify expected + interrupt actual → justify, no warn", () => {
    expect(resolveAction("justify", "interrupt")).toEqual({ action: "justify", warn: null });
  });
  it("plain expected + answer actual → none, no warn", () => {
    expect(resolveAction("plain", "answer")).toEqual({ action: "none", warn: null });
  });

  // 불일치: 크래시 대신 경고 + 진행 (감지 후 반응)
  it("clarify expected but answer actual → none + warn (clarify 미발생)", () => {
    const r = resolveAction("clarify", "answer");
    expect(r.action).toBe("none");
    expect(r.warn).toMatch(/clarify/);
  });
  it("justify expected but answer actual → none + warn (승인 카드 미발생)", () => {
    const r = resolveAction("justify", "answer");
    expect(r.action).toBe("none");
    expect(r.warn).not.toBeNull();
  });
  it("plain expected but clarify actual → clarifyOption + warn (예상치 못한 clarify, 언블록)", () => {
    const r = resolveAction("plain", "clarify");
    expect(r.action).toBe("clarifyOption");
    expect(r.warn).not.toBeNull();
  });
  it("justify expected but clarify actual → clarifyOption + warn", () => {
    const r = resolveAction("justify", "clarify");
    expect(r.action).toBe("clarifyOption");
    expect(r.warn).not.toBeNull();
  });
  it("plain expected but interrupt actual → none + warn", () => {
    const r = resolveAction("plain", "interrupt");
    expect(r.action).toBe("none");
    expect(r.warn).not.toBeNull();
  });
});
