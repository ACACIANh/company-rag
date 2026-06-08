export type SceneKind =
  | "capability"
  | "permission"
  | "rag"
  | "clarify"
  | "rag_block"
  | "sql_read"
  | "sql_write"
  | "sql_write_deny"
  | "permission_delegate"
  | "audit";

export interface Scene {
  id: string;
  account: string;
  password: string;
  display_name: string;
  dept: string | null;
  question: string;
  kind: SceneKind;
  resume_text: string | null;
}
