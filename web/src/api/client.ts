import { ApiError, Session, SessionMessage, SSEEvent } from "../types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

let onUnauthorized: (() => void) | null = null;

export function setOnUnauthorized(handler: (() => void) | null): void {
  onUnauthorized = handler;
}

interface ApiFetchOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: unknown;
  headers?: Record<string, string>;
}

export async function apiFetch<T = unknown>(
  path: string,
  options: ApiFetchOptions = {}
): Promise<T> {
  const { method = "GET", body, headers = {} } = options;
  const finalHeaders: Record<string, string> = { ...headers };

  const token = localStorage.getItem("token");
  if (token) {
    finalHeaders["Authorization"] = `Bearer ${token}`;
  }

  let serializedBody: string | undefined;
  if (body !== undefined) {
    serializedBody = JSON.stringify(body);
    finalHeaders["Content-Type"] = "application/json";
  }

  const response = await fetch(`${BASE_URL}${path}`, {
    method,
    headers: finalHeaders,
    body: serializedBody,
  });

  if (response.status === 401) {
    if (onUnauthorized) onUnauthorized();
    throw new ApiError(401, await safeMessage(response));
  }

  if (response.status === 429) {
    const retryAfterRaw = response.headers.get("Retry-After");
    const retryAfter = retryAfterRaw ? Number(retryAfterRaw) : undefined;
    throw new ApiError(429, await safeMessage(response), retryAfter);
  }

  if (!response.ok) {
    throw new ApiError(response.status, await safeMessage(response));
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

async function safeMessage(response: Response): Promise<string> {
  try {
    const data = await response.json();
    if (typeof data === "object" && data && "detail" in data) {
      return String((data as { detail: unknown }).detail);
    }
    return JSON.stringify(data);
  } catch {
    return response.statusText || `HTTP ${response.status}`;
  }
}

export async function getSessions(): Promise<Session[]> {
  return apiFetch<Session[]>("/sessions");
}

export async function getSessionMessages(sessionId: string): Promise<SessionMessage[]> {
  return apiFetch<SessionMessage[]>(`/sessions/${sessionId}/messages`);
}

export async function deleteSession(sessionId: string): Promise<void> {
  return apiFetch<void>(`/sessions/${sessionId}`, { method: "DELETE" });
}

export async function* streamChat(
  question: string,
  sessionId: string | null
): AsyncGenerator<SSEEvent> {
  const token = localStorage.getItem("token");
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const response = await fetch(`${BASE_URL}/chat/stream`, {
    method: "POST",
    headers,
    body: JSON.stringify({ question, session_id: sessionId }),
  });

  if (response.status === 401) {
    if (onUnauthorized) onUnauthorized();
    throw new ApiError(401, await safeMessage(response));
  }
  if (!response.ok) {
    throw new ApiError(response.status, await safeMessage(response));
  }

  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      const line = part.replace(/^data: /, "").trim();
      if (line) yield JSON.parse(line) as SSEEvent;
    }
  }
}
