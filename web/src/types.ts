export interface TokenRequest {
  username: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface AuthUser {
  user_id: string;
  roles: string[];
  departments: string[];
}

export interface ChatRequest {
  question: string;
  session_id: string | null;
}

export interface ChatResponse {
  answer: string;
  sources: string[];
  session_id: string;
  tools?: string[];
}

export type ChatRole = "user" | "assistant";

export interface InterruptAction {
  tool: string;
  planned_action: string;
}

export interface ClarifyPayload {
  message: string;
  options: string[];
}

export interface ChatMessage {
  role: ChatRole;
  content: string;
  sources?: string[];
  route?: string;
  tools?: string[];
  streaming?: boolean;
  interrupt?: InterruptAction[];
  clarify?: ClarifyPayload;
}

export class ApiError extends Error {
  status: number;
  retryAfter?: number;

  constructor(status: number, message: string, retryAfter?: number) {
    super(message);
    this.status = status;
    this.retryAfter = retryAfter;
  }
}

export interface Session {
  thread_id: string;
  title: string;
  created_at: string; // ISO8601
}

export interface SessionMessage {
  role: ChatRole;
  content: string;
  sources?: string[];
}

export type SSEEvent =
  | { type: "token";     content: string }
  | { type: "sources";   sources: string[]; route?: string; tools?: string[] }
  | { type: "done";      session_id: string }
  | { type: "error";     message: string }
  | { type: "interrupt"; actions: InterruptAction[] }
  | { type: "clarify";   message: string; options: string[] };
