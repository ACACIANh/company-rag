import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../types";
import { useAuth } from "./AuthContext";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(username, password);
      navigate("/chat", { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.status === 401 ? "아이디 또는 비밀번호가 올바르지 않습니다." : err.message);
      } else {
        setError("네트워크 오류가 발생했습니다.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen gradient-mesh flex flex-col items-center justify-center px-4">
      {/* Logo area */}
      <div className="mb-8 text-center">
        <h1
          className="text-[32px] font-light text-ink tracking-[-0.64px]"
          style={{ fontFeatureSettings: '"ss01"' }}
        >
          Friday
        </h1>
        <p className="mt-1 text-[15px] text-ink-mute font-light">
          사내 문서 AI 어시스턴트
        </p>
      </div>

      {/* Card */}
      <form
        onSubmit={onSubmit}
        className="w-full max-w-sm bg-canvas rounded-xl border border-hairline px-8 py-8 space-y-5"
        style={{ boxShadow: "rgba(0,55,112,0.08) 0 8px 24px, rgba(0,55,112,0.04) 0 2px 6px" }}
      >
        <div className="space-y-4">
          <label className="block">
            <span className="text-[13px] font-normal text-ink-mute tracking-[-0.39px]">아이디</span>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="mt-1 block w-full rounded-[6px] border border-hairline-input bg-canvas text-ink text-[15px] font-light px-3 py-2 outline-none focus:border-primary transition-colors"
              autoComplete="username"
              required
            />
          </label>
          <label className="block">
            <span className="text-[13px] font-normal text-ink-mute tracking-[-0.39px]">비밀번호</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-1 block w-full rounded-[6px] border border-hairline-input bg-canvas text-ink text-[15px] font-light px-3 py-2 outline-none focus:border-primary transition-colors"
              autoComplete="current-password"
              required
            />
          </label>
        </div>

        {error && (
          <p className="text-[13px] text-ruby font-normal">{error}</p>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="w-full bg-primary hover:bg-primary-deep active:bg-primary-press text-canvas font-normal text-[16px] rounded-pill py-2 transition-colors disabled:opacity-50"
        >
          {submitting ? "로그인 중…" : "로그인"}
        </button>
      </form>
    </div>
  );
}
