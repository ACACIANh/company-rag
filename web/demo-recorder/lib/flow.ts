import type { Scene } from "./types";

export type Interaction = "clarify" | "justify" | "plain";

export function needsRelogin(prevAccount: string | null, nextAccount: string): boolean {
  return prevAccount !== nextAccount;
}

export function interactionFor(scene: Scene): Interaction {
  if (scene.kind === "clarify") return "clarify";
  if (scene.resume_text !== null) return "justify";
  return "plain";
}

/** 한 턴이 실제로 도달한 UI 상태(이번 턴의 결과). */
export type TurnOutcome = "clarify" | "interrupt" | "answer";

/** 기대한 상호작용과 실제 결과로부터 레코더가 취할 동작. */
export type Action = "clarifyOption" | "justify" | "none";

/**
 * 기대(expected)와 실제 UI 결과(actual)를 비교해 동작을 결정한다.
 * LLM 라우터/게이트는 경계에서 비결정적이므로, 불일치 시 크래시 대신
 * 경고를 남기고 가능한 한 진행한다(demo_bench의 감지-후-반응과 동일 철학).
 */
export function resolveAction(
  expected: Interaction,
  actual: TurnOutcome,
): { action: Action; warn: string | null } {
  if (expected === "clarify") {
    if (actual === "clarify") return { action: "clarifyOption", warn: null };
    if (actual === "answer")
      return { action: "none", warn: "clarify 미발생 — 일반 응답으로 진행" };
    return { action: "none", warn: "clarify 기대했으나 승인 카드 발생 — 그대로 진행" };
  }
  if (expected === "justify") {
    if (actual === "interrupt") return { action: "justify", warn: null };
    if (actual === "clarify")
      return { action: "clarifyOption", warn: "justify 기대했으나 clarify 발생 — 옵션 선택으로 진행" };
    return { action: "none", warn: "승인 카드 미발생(거부/미게이트?) — 그대로 진행" };
  }
  // expected === "plain"
  if (actual === "answer") return { action: "none", warn: null };
  if (actual === "clarify")
    return { action: "clarifyOption", warn: "예상치 못한 clarify — 옵션 선택으로 언블록" };
  return { action: "none", warn: "예상치 못한 승인 카드 — 그대로 진행" };
}
