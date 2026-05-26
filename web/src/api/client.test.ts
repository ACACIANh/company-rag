import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { ApiError, SSEEvent } from "../types";
import { apiFetch, setOnUnauthorized, streamChat } from "./client";

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

describe("streamChat", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function makeStreamResponse(lines: string[]): Response {
    const body = lines.join("\n\n") + "\n\n";
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(body));
        controller.close();
      },
    });
    return new Response(stream, {
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
    });
  }

  test("yields token events from SSE stream", async () => {
    localStorage.setItem("token", "test-token");
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      makeStreamResponse([
        'data: {"type":"token","content":"안녕"}',
        'data: {"type":"token","content":"하세요"}',
        'data: {"type":"sources","sources":["doc.md"]}',
        'data: {"type":"done","session_id":"abc"}',
      ])
    );

    const events: SSEEvent[] = [];
    for await (const event of streamChat("테스트", null)) {
      events.push(event);
    }

    expect(events).toHaveLength(4);
    expect(events[0]).toEqual({ type: "token", content: "안녕" });
    expect(events[3]).toEqual({ type: "done", session_id: "abc" });
  });

  test("throws ApiError on 401", async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      new Response(JSON.stringify({ detail: "Unauthorized" }), { status: 401 })
    );

    await expect(async () => {
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      for await (const _ of streamChat("질문", null)) { /* noop */ }
    }).rejects.toBeInstanceOf(ApiError);
  });
});
