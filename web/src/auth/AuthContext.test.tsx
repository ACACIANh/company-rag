import { act, render, renderHook, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { AuthProvider, useAuth } from "./AuthContext";

describe("AuthContext", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  test("starts unauthenticated when no token present", () => {
    const { result } = renderHook(() => useAuth(), {
      wrapper: ({ children }) => <AuthProvider>{children}</AuthProvider>,
    });
    expect(result.current.user).toBeNull();
    expect(result.current.token).toBeNull();
  });

  test("login stores token + fetches /auth/me + sets user", async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ access_token: "tok", token_type: "bearer" }), { status: 200 })
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ user_id: "u1", roles: ["user"], allowed_doc_ids: ["d1"] }),
          { status: 200 }
        )
      );

    const { result } = renderHook(() => useAuth(), {
      wrapper: ({ children }) => <AuthProvider>{children}</AuthProvider>,
    });

    await act(async () => {
      await result.current.login("alice", "pw");
    });

    expect(localStorage.getItem("token")).toBe("tok");
    expect(result.current.user?.user_id).toBe("u1");
    expect(result.current.token).toBe("tok");
  });

  test("logout clears token, session_id, user", async () => {
    localStorage.setItem("token", "tok");
    localStorage.setItem("session_id", "sess-1");
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      new Response(
        JSON.stringify({ user_id: "u1", roles: [], allowed_doc_ids: [] }),
        { status: 200 }
      )
    );

    const { result } = renderHook(() => useAuth(), {
      wrapper: ({ children }) => <AuthProvider>{children}</AuthProvider>,
    });

    await waitFor(() => expect(result.current.user?.user_id).toBe("u1"));

    act(() => {
      result.current.logout();
    });

    expect(localStorage.getItem("token")).toBeNull();
    expect(localStorage.getItem("session_id")).toBeNull();
    expect(result.current.user).toBeNull();
    expect(result.current.token).toBeNull();
  });

  test("renders children", () => {
    render(
      <AuthProvider>
        <div>child</div>
      </AuthProvider>
    );
    expect(screen.getByText("child")).toBeInTheDocument();
  });
});
