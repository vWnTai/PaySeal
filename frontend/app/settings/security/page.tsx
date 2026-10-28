"use client";

import { FormEvent, useState } from "react";
import { Shell } from "@/components/Shell";
import { Icon } from "@/components/Icon";
import { api } from "@/lib/api";
import { LoadingButton } from "@/components/LoadingButton";
import { useSession } from "@/components/SessionProvider";

type Setup = { secret: string; provisioning_uri: string };

export default function Security() {
  const { user, reloadUser } = useSession();
  const [setup, setSetup] = useState<Setup | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function begin() {
    setError("");
    setBusy(true);
    try {
      setSetup(await api<Setup>("/auth/mfa/setup", { method: "POST" }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không thể bắt đầu cài đặt");
    } finally {
      setBusy(false);
    }
  }
  async function enable(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setBusy(true);
    const code = new FormData(event.currentTarget).get("code");
    try {
      await api("/auth/mfa/enable", { method: "POST", body: JSON.stringify({ code }) });
      setMessage("Đã bật xác thực hai bước.");
      setSetup(null);
      await reloadUser();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Mã xác thực không hợp lệ");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Shell title="Bảo mật" description="Bảo vệ tài khoản và các thao tác phê duyệt quan trọng.">
      <section className="card max-w-2xl">
        <div className="flex items-start gap-3">
          <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-teal-50 text-teal-700">
            <Icon name="key" size={22} />
          </span>
          <div>
            <h2 className="section-title">Xác thực hai bước (MFA)</h2>
            <p className="muted mt-1">
              Dùng ứng dụng tạo mã 6 số để bảo vệ đăng nhập và phê duyệt giá trị cao.
            </p>
          </div>
        </div>
        {error && (
          <div role="alert" className="alert-error mt-5">
            <Icon name="alert" size={20} />
            <span>{error}</span>
          </div>
        )}
        {message && (
          <div role="status" className="alert-success mt-5">
            <Icon name="check" size={20} />
            <span>{message}</span>
          </div>
        )}
        {user?.mfa_enabled ? (
          <div className="alert-success mt-6">
            <Icon name="shield" size={20} />
            <div>
              <strong>Xác thực hai bước đang bật</strong>
              <p className="mt-1">Tài khoản được bảo vệ bằng mã từ ứng dụng xác thực.</p>
            </div>
          </div>
        ) : !setup ? (
          <LoadingButton
            type="button"
            onClick={begin}
            busy={busy}
            busyLabel="Đang chuẩn bị..."
            className="btn-primary mt-6"
          >
            Thiết lập MFA
          </LoadingButton>
        ) : (
          <form onSubmit={enable} className="mt-6 space-y-5">
            <p className="muted">
              Mở ứng dụng xác thực trên điện thoại, chọn thêm tài khoản bằng khóa thiết lập, rồi
              nhập khóa bên dưới. Tiếp theo nhập mã 6 số vừa được tạo.
            </p>
            <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
              <p className="font-semibold text-amber-950">Lưu khóa thiết lập ngay</p>
              <p className="mt-1 text-sm text-amber-900">
                Khóa này chỉ hiển thị trong quá trình cài đặt. Không chia sẻ với người khác.
              </p>
              <code className="mt-3 block break-all rounded-lg bg-white p-3 text-sm text-slate-900">
                {setup.secret}
              </code>
            </div>
            <label>
              <span className="label">Mã 6 số từ ứng dụng xác thực</span>
              <input
                name="code"
                inputMode="numeric"
                pattern="[0-9]{6}"
                autoComplete="one-time-code"
                required
                maxLength={6}
                placeholder="000000"
              />
            </label>
            <LoadingButton busy={busy} busyLabel="Đang xác minh...">
              Xác minh và bật MFA
            </LoadingButton>
          </form>
        )}
      </section>
    </Shell>
  );
}
