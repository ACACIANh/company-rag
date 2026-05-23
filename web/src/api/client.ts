import { ApiError } from "../types";

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
