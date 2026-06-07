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
