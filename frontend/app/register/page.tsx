"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { AuthFrame } from "@/components/AuthFrame";
import { Icon } from "@/components/Icon";
import { api } from "@/lib/api";
import { LoadingButton } from "@/components/LoadingButton";
import { PasswordField } from "@/components/PasswordField";

export default function Register() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(event.currentTarget);
    try {
      await api(
        "/auth/register",
        {
          method: "POST",
          body: JSON.stringify({
            full_name: data.get("name"),
            email: data.get("email"),
            password: data.get("password"),
          }),
        },
        false,
      );
      router.push("/login?created=1");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không thể tạo tài khoản");
    } finally {
      setBusy(false);
    }
  }
  return (
    <AuthFrame
      title="Tạo tài khoản"
      description="Bắt đầu với một không gian làm việc an toàn cho tổ chức của bạn."
    >
      <form onSubmit={submit} className="space-y-5">
        {error && (
          <div role="alert" className="alert-error">
            <Icon name="alert" size={20} />
            <span>{error}</span>
          </div>
        )}
        <label>
          <span className="label">Họ và tên</span>
          <input
            name="name"
            required
            minLength={2}
            autoComplete="name"
            placeholder="Nguyễn Văn A"
          />
        </label>
        <label>
          <span className="label">Email công việc</span>
          <input
            name="email"
            type="email"
            required
            autoComplete="email"
            placeholder="ban@congty.vn"
          />
        </label>
        <PasswordField
          name="password"
          required
          minLength={12}
          maxLength={128}
          autoComplete="new-password"
          placeholder="Tối thiểu 12 ký tự"
          hint="Dùng ít nhất 12 ký tự để bảo vệ tài khoản."
        />
        <LoadingButton busy={busy} busyLabel="Đang tạo..." className="btn-primary w-full">
          Tạo tài khoản
          <Icon name="arrowRight" size={18} />
        </LoadingButton>
        <p className="text-center text-sm text-slate-600">
          Đã có tài khoản?{" "}
          <Link className="font-semibold text-teal-700 hover:underline" href="/login">
            Đăng nhập
          </Link>
        </p>
      </form>
    </AuthFrame>
  );
}
