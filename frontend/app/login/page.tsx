"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AuthFrame } from "@/components/AuthFrame";
import { Icon } from "@/components/Icon";
import { api, ApiError, saveSession } from "@/lib/api";
import { LoadingButton } from "@/components/LoadingButton";
import { PasswordField } from "@/components/PasswordField";
import type { LoginResponse, User } from "@/types";

type Credentials = { email: string; password: string };

export default function Login() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  // Keep credentials only in memory until MFA succeeds or the user goes back.
  const [credentials, setCredentials] = useState<Credentials | null>(null);
  const [email, setEmail] = useState("");
  const [totp, setTotp] = useState("");
  const [registered, setRegistered] = useState(false);
  useEffect(() => {
    setRegistered(new URLSearchParams(window.location.search).get("created") === "1");
  }, []);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    const data = new FormData(event.currentTarget);
    const account = credentials || { email: email.trim(), password: String(data.get("password")) };
    try {
      const result = await api<LoginResponse>(
        "/auth/login",
        {
          method: "POST",
          body: JSON.stringify({
            ...account,
            ...(credentials ? { totp_code: totp } : {}),
          }),
        },
        false,
      );
      saveSession(result);
      localStorage.removeItem("payseal_org");
      const me = await api<User>("/auth/me");
      if (me.organizations[0]) localStorage.setItem("payseal_org", me.organizations[0].id);
      setCredentials(null);
      setTotp("");
      router.push(
        me.is_platform_reviewer
          ? "/platform/verifications"
          : me.organizations.length
            ? "/dashboard"
            : "/organization",
      );
    } catch (reason) {
      if (!credentials && reason instanceof ApiError && reason.code === "MFA_REQUIRED") {
        setCredentials(account);
        setTotp("");
      } else {
        setError(reason instanceof Error ? reason.message : "Đăng nhập không thành công");
      }
    } finally {
      setBusy(false);
    }
  }
  return (
    <AuthFrame
      title={credentials ? "Xác thực hai bước" : "Đăng nhập"}
      description={
        credentials
          ? "Chỉ còn một bước để đăng nhập an toàn vào tài khoản của bạn."
          : "Tiếp tục quản lý và xác minh yêu cầu thanh toán."
      }
    >
      <form key={credentials ? "mfa" : "login"} onSubmit={submit} className="space-y-5 page-enter">
        {registered && !credentials && (
          <div className="alert-success" role="status">
            <Icon name="check" size={20} />
            <span>Tài khoản đã được tạo. Đăng nhập để bắt đầu.</span>
          </div>
        )}
        {error && (
          <div role="alert" className="alert-error">
            <Icon name="alert" size={20} />
            <span>{error}</span>
          </div>
        )}
        {credentials ? (
          <>
            <div
              className="flex items-center gap-3 rounded-2xl border border-teal-100 bg-teal-50/70 p-4"
              role="status"
            >
              <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-white text-teal-700 shadow-sm">
                <Icon name="shield" size={24} />
              </span>
              <div className="min-w-0">
                <p className="text-xs font-medium text-teal-700">Mật khẩu đã được xác nhận</p>
                <p className="mt-1 break-all text-sm font-semibold text-slate-800">
                  {credentials.email}
                </p>
              </div>
            </div>
            <div>
              <label htmlFor="login-totp">
                <span className="label">Mã xác thực</span>
                <input
                  id="login-totp"
                  name="totp"
                  type="text"
                  inputMode="numeric"
                  pattern="[0-9]{6}"
                  required
                  autoFocus
                  autoComplete="one-time-code"
                  placeholder="000000"
                  value={totp}
                  onChange={(event) => {
                    setTotp(event.target.value.replace(/\D/g, "").slice(0, 6));
                    setError("");
                  }}
                  aria-describedby="mfa-hint"
                  aria-invalid={Boolean(error)}
                  disabled={busy}
                  className="py-4 text-center font-mono text-2xl tracking-[0.35em]"
                />
              </label>
              <span id="mfa-hint" className="hint">
                Mở ứng dụng xác thực của bạn và nhập mã 6 số đang hiển thị.
              </span>
            </div>
          </>
        ) : (
          <>
            <label>
              <span className="label">Email</span>
              <input
                name="email"
                type="email"
                required
                autoComplete="username"
                placeholder="ban@congty.vn"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                disabled={busy}
              />
            </label>
            <PasswordField
              name="password"
              required
              autoComplete="current-password"
              placeholder="Nhập mật khẩu"
              disabled={busy}
            />
          </>
        )}
        <LoadingButton
          busy={busy}
          busyLabel={credentials ? "Đang xác thực..." : "Đang đăng nhập..."}
          disabled={Boolean(credentials) && totp.length !== 6}
          className="btn-primary w-full"
        >
          {credentials ? "Xác nhận và đăng nhập" : "Đăng nhập"}
          <Icon name="arrowRight" size={18} />
        </LoadingButton>
        {credentials ? (
          <button
            type="button"
            className="btn-quiet w-full"
            disabled={busy}
            onClick={() => {
              setCredentials(null);
              setTotp("");
              setError("");
            }}
          >
            <Icon name="arrowLeft" size={16} />
            Quay lại đăng nhập
          </button>
        ) : (
          <p className="text-center text-sm text-slate-600">
            Chưa có tài khoản?{" "}
            <Link className="font-semibold text-teal-700 hover:underline" href="/register">
              Đăng ký ngay
            </Link>
          </p>
        )}
      </form>
    </AuthFrame>
  );
}
