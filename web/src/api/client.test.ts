import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { ApiError } from "../types";
import { apiFetch, setOnUnauthorized } from "./client";

describe("apiFetch", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    setOnUnauthorized(null);
  });

  test("attaches Authorization Bearer when token exists", async () => {
    localStorage.setItem("token", "abc.def.ghi");
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 })
    );

    await apiFetch("/auth/me");

    const [, init] = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect((init.headers as Record<string, string>)["Authorization"]).toBe(
      "Bearer abc.def.ghi"
    );
  });

  test("omits Authorization when token missing", async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 })
    );

    await apiFetch("/auth/token", { method: "POST", body: { username: "u", password: "p" } });

    const [, init] = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect((init.headers as Record<string, string>)["Authorization"]).toBeUndefined();
  });

  test("calls onUnauthorized and throws ApiError on 401", async () => {
    localStorage.setItem("token", "expired");
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      new Response(JSON.stringify({ detail: "Invalid" }), { status: 401 })
    );
    const onUnauth = vi.fn();
    setOnUnauthorized(onUnauth);

    await expect(apiFetch("/chat", { method: "POST", body: { question: "x", session_id: null } })).rejects.toBeInstanceOf(ApiError);
    expect(onUnauth).toHaveBeenCalledOnce();
  });

  test("parses Retry-After on 429 into ApiError.retryAfter", async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      new Response(JSON.stringify({ detail: "Too many" }), {
        status: 429,
        headers: { "Retry-After": "60" },
      })
    );

    try {
      await apiFetch("/chat", { method: "POST", body: { question: "x", session_id: null } });
      throw new Error("should have thrown");
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).status).toBe(429);
      expect((err as ApiError).retryAfter).toBe(60);
    }
  });

  test("serializes JSON body and sets Content-Type", async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 })
    );

    await apiFetch("/chat", { method: "POST", body: { question: "hi", session_id: null } });

    const [, init] = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(init.method).toBe("POST");
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
    expect(JSON.parse(init.body as string)).toEqual({ question: "hi", session_id: null });
  });
});
