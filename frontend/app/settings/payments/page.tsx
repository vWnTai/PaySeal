"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { Shell } from "@/components/Shell";
import { Icon } from "@/components/Icon";
import { Feedback } from "@/components/Feedback";
import { LoadingButton } from "@/components/LoadingButton";
import { useSession } from "@/components/SessionProvider";
import { api, session } from "@/lib/api";
import { useApiQuery } from "@/lib/useApiQuery";
import { readinessLabels } from "@/lib/operations";
import type { PaymentChannel, PaymentReadiness } from "@/types";

export default function PaymentSettings() {
  const { user } = useSession();
  const [organizationId, setOrganizationId] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [disconnectId, setDisconnectId] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  useEffect(() => setOrganizationId(session().organizationId), []);
  const role = user?.organizations.find((item) => item.id === organizationId)?.role;
  const owner = role === "OWNER";
  const readiness = useApiQuery<PaymentReadiness>(
    organizationId ? "/payment-integrations/status" : null,
  );
  const channels = useApiQuery<PaymentChannel[]>(
    organizationId && (owner || role === "AUDITOR") ? "/payment-integrations/channels" : null,
  );
  const ready = readiness.data;
  const canConnect =
    owner && ready?.infrastructure_ready && ready.business_verified && user?.mfa_enabled;

  async function connect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    setBusy("connect");
    setError("");
    setNotice("");
    try {
      await api("/payment-integrations/channels", {
        method: "POST",
        body: JSON.stringify({
          purpose: data.get("purpose"),
          client_id: data.get("client_id"),
          api_key: data.get("api_key"),
          checksum_key: data.get("checksum_key"),
          bank_bin: data.get("bank_bin"),
          account_number: data.get("account_number"),
          account_name: data.get("account_name"),
          totp_code: data.get("totp"),
          attested: data.get("attested") === "on",
        }),
      });
      form.reset();
      setShowForm(false);
      setNotice(
        "Đã đối chiếu tài khoản với payOS và kết nối kênh. Chưa có lệnh chi hoặc khoản thu nào được tạo.",
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không thể kết nối kênh.");
    } finally {
      await Promise.all([readiness.reload(), channels.reload()]);
      setBusy("");
    }
  }

  async function disconnect(event: FormEvent<HTMLFormElement>, channelId: string) {
    event.preventDefault();
    if (busy) return;
    const data = new FormData(event.currentTarget);
    setBusy(channelId);
    setError("");
    setNotice("");
    try {
      await api("/payment-integrations/channels/" + channelId + "/disconnect", {
        method: "POST",
        body: JSON.stringify({
          reason: "Chủ tổ chức chủ động yêu cầu ngắt kênh thanh toán hiện tại.",
          totp_code: data.get("totp"),
        }),
      });
      setDisconnectId("");
      await Promise.all([readiness.reload(), channels.reload()]);
      setNotice(
        "Đã ngắt kênh cho giao dịch mới. Lịch sử cũ vẫn được giữ để đối soát; lệnh đã gửi không tự bị hủy.",
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không thể ngắt kênh.");
    } finally {
      setBusy("");
    }
  }

  return (
    <Shell
      title="Kết nối thanh toán"
      description="Một lộ trình rõ ràng để chuyển từ thử nghiệm sang thu và chi tiền qua payOS."
    >
      <section className="card mb-6 overflow-hidden border-teal-200 bg-linear-to-br from-teal-50 via-white to-sky-50">
        <div className="flex flex-wrap items-start justify-between gap-5">
          <div className="max-w-2xl">
            <span className="badge border-teal-200 bg-white text-teal-800">
              TÍCH HỢP payOS · THU & CHI
            </span>
            <h2 className="mt-4 text-2xl font-bold tracking-tight text-slate-900">
              Bắt đầu từng bước, không cần chọn lại công nghệ
            </h2>
            <p className="muted mt-3 leading-relaxed">
              Bạn chưa có ngân hàng hoặc máy chủ vẫn có thể hoàn thiện hồ sơ và thử quy trình. Giao
              dịch thật chỉ mở khi hạ tầng và kênh thanh toán đã sẵn sàng.
            </p>
          </div>
          <Icon name="wallet" size={36} className="text-teal-700" />
        </div>
        <div className="mt-5 flex flex-wrap gap-3">
          <a
            href="https://my.payos.vn"
            target="_blank"
            rel="noopener noreferrer"
            className="btn-primary"
          >
            Mở trang đăng ký payOS <Icon name="arrowRight" size={17} />
          </a>
          <Link href="/transfers" className="btn-secondary">
            Xem luồng chi tiền
          </Link>
        </div>
        <p className="hint mt-4">
          Không gửi khóa API trong cuộc trò chuyện. Chỉ nhập vào ứng dụng của bạn trên tên miền
          HTTPS đã kiểm tra.
        </p>
      </section>
      <Feedback
        loading={readiness.loading || channels.loading}
        error={readiness.error || channels.error}
        retry={() => {
          void readiness.reload();
          void channels.reload();
        }}
      />
      {error && (
        <div role="alert" className="alert-error mb-5">
          <Icon name="alert" />
          <span>{error}</span>
        </div>
      )}
      {notice && (
        <div role="status" className="alert-success mb-5">
          <Icon name="check" />
          <span>{notice}</span>
        </div>
      )}
      <div className="mb-6 grid gap-4 md:grid-cols-3">
        <section className="card">
          <p className="hint font-semibold text-teal-700">BƯỚC 1 · PHÁP NHÂN & TÀI KHOẢN</p>
          <h3 className="section-title mt-3">Hồ sơ đúng, tài khoản đúng</h3>
          <p className="muted mt-2">
            Mở tài khoản phù hợp với pháp nhân của bạn, đăng ký payOS và hoàn tất xác minh theo yêu
            cầu nhà cung cấp.
          </p>
          <p className="mt-3 text-sm font-semibold text-slate-700">
            Hồ sơ PaySeal: {ready?.business_verified ? "đã xét duyệt" : "chưa hoàn tất"}
          </p>
          <Link href="/organization/verification" className="btn-quiet mt-3">
            Xem hồ sơ <Icon name="arrowRight" size={16} />
          </Link>
        </section>
        <section className="card">
          <p className="hint font-semibold text-teal-700">BƯỚC 2 · WEBSITE AN TOÀN</p>
          <h3 className="section-title mt-3">Tên miền & HTTPS</h3>
          <p className="muted mt-2">
            Triển khai lên máy chủ có tên miền công khai, HTTPS, khóa riêng và sao lưu. Website chạy
            trên localhost chưa nhận được webhook từ payOS.
          </p>
          <p className="mt-3 text-sm font-semibold text-slate-700">
            Hạ tầng: {ready?.infrastructure_ready ? "đủ điều kiện kỹ thuật" : "chưa sẵn sàng"}
          </p>
          {!user?.mfa_enabled && (
            <Link href="/settings/security" className="btn-quiet mt-3">
              Bật xác thực hai bước
            </Link>
          )}
        </section>
        <section className="card">
          <p className="hint font-semibold text-teal-700">BƯỚC 3 · KÊNH THANH TOÁN</p>
          <h3 className="section-title mt-3">Kết nối thu & chi riêng</h3>
          <p className="muted mt-2">
            Tạo kênh thu, rồi đăng ký kích hoạt kênh chi với payOS. Mỗi kênh có bộ khóa riêng; quyền
            chi không tự có từ kênh thu.
          </p>
          <p className="mt-3 text-sm font-semibold text-slate-700">
            Thu: {ready?.collection_connected ? "đã nối" : "chưa nối"} · Chi:{" "}
            {ready?.payout_connected ? "đã nối" : "chưa nối"}
          </p>
          {owner && (
            <button
              type="button"
              className="btn-secondary mt-3"
              disabled={!canConnect}
              onClick={() => setShowForm(!showForm)}
            >
              Tôi đã có khóa API
            </button>
          )}
        </section>
      </div>
      {ready && ready.blockers.length > 0 && (
        <details className="card mb-6">
          <summary className="cursor-pointer font-semibold text-slate-800">
            Những điều kiện quản trị cần hoàn tất ({ready.blockers.length})
          </summary>
          <ul className="mt-4 space-y-2">
            {ready.blockers.map((code) => (
              <li className="flex items-start gap-2 text-sm text-slate-600" key={code}>
                <Icon name="alert" size={16} className="mt-0.5 shrink-0 text-amber-600" />
                {readinessLabels[code] || code}
              </li>
            ))}
          </ul>
        </details>
      )}
      {showForm && canConnect && (
        <form className="card mb-6 max-w-3xl" onSubmit={connect} autoComplete="off">
          <h2 className="section-title">Kết nối kênh của tổ chức</h2>
          <p className="muted mt-2">
            Tên tài khoản cần khớp tên payOS trả về. Hệ thống kiểm tra tài khoản, không chuyển thử
            tiền khi kết nối.
          </p>
          <fieldset disabled={Boolean(busy)} className="mt-5 grid gap-4 sm:grid-cols-2">
            <label className="sm:col-span-2">
              <span id="channel-purpose-label" className="label">
                Loại kênh
              </span>
              <select name="purpose" aria-labelledby="channel-purpose-label">
                <option value="COLLECTION">Kênh thu — nhận tiền về tổ chức</option>
                <option value="PAYOUT">Kênh chi — tài khoản nguồn đã được payOS kích hoạt</option>
              </select>
            </label>
            <label>
              <span className="label">Client ID</span>
              <input name="client_id" required minLength={8} maxLength={200} autoComplete="off" />
            </label>
            <label>
              <span className="label">API Key</span>
              <input
                name="api_key"
                type="password"
                required
                minLength={16}
                maxLength={300}
                autoComplete="new-password"
              />
            </label>
            <label className="sm:col-span-2">
              <span className="label">Checksum Key</span>
              <input
                name="checksum_key"
                type="password"
                required
                minLength={16}
                maxLength={300}
                autoComplete="new-password"
              />
            </label>
            <label>
              <span className="label">BIN ngân hàng (6 số)</span>
              <input
                name="bank_bin"
                required
                pattern="[0-9]{6}"
                inputMode="numeric"
                maxLength={6}
              />
            </label>
            <label>
              <span className="label">Số tài khoản kênh</span>
              <input
                name="account_number"
                required
                pattern="[0-9]+"
                minLength={4}
                maxLength={34}
                inputMode="numeric"
                autoComplete="off"
              />
            </label>
            <label className="sm:col-span-2">
              <span className="label">Tên chủ tài khoản theo payOS</span>
              <input name="account_name" required minLength={2} maxLength={200} />
            </label>
            <label>
              <span className="label">Mã xác thực 6 số</span>
              <input
                name="totp"
                required
                pattern="[0-9]{6}"
                maxLength={6}
                inputMode="numeric"
                autoComplete="one-time-code"
              />
            </label>
            <label className="flex items-start gap-3 sm:col-span-2">
              <input name="attested" type="checkbox" required className="mt-1 size-4" />
              <span className="text-sm leading-relaxed text-slate-700">
                Tôi có quyền quản lý kênh này cho tổ chức đang chọn và đã kiểm tra pháp nhân, tài
                khoản cùng quyền dịch vụ với payOS.
              </span>
            </label>
            <div className="flex flex-wrap gap-3 sm:col-span-2">
              <LoadingButton busy={busy === "connect"} busyLabel="Đang kiểm tra kênh...">
                Kiểm tra & kết nối
              </LoadingButton>
              <button type="button" className="btn-quiet" onClick={() => setShowForm(false)}>
                Hủy
              </button>
            </div>
          </fieldset>
        </form>
      )}
      {channels.data && channels.data.length > 0 && (
        <section className="space-y-4">
          <h2 className="section-title">Các kênh đã cấu hình</h2>
          {channels.data.map((item) => (
            <article key={item.id} className="card">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <h3 className="font-semibold text-slate-900">
                    {item.purpose === "COLLECTION" ? "Kênh thu" : "Kênh chi"} · {item.account_name}
                  </h3>
                  <p className="muted mt-2">
                    BIN {item.bank_bin} · ******{item.account_last4}
                  </p>
                </div>
                <span className="badge">
                  {item.status === "ACTIVE"
                    ? "Đã kết nối"
                    : item.status === "CONFIGURING"
                      ? "Đang xác minh kết nối"
                      : "Đã ngắt"}
                </span>
              </div>
              {owner && item.status !== "DISABLED" && (
                <button
                  type="button"
                  className="btn-quiet mt-4 text-red-700"
                  onClick={() => setDisconnectId(item.id)}
                >
                  Ngắt kênh cho giao dịch mới
                </button>
              )}
              {disconnectId === item.id && (
                <form
                  onSubmit={(event) => disconnect(event, item.id)}
                  className="mt-4 flex flex-wrap items-end gap-3"
                >
                  <label>
                    <span className="label">Mã xác thực để ngắt kênh</span>
                    <input
                      name="totp"
                      required
                      pattern="[0-9]{6}"
                      inputMode="numeric"
                      maxLength={6}
                      autoComplete="one-time-code"
                    />
                  </label>
                  <LoadingButton busy={busy === item.id} busyLabel="Đang ngắt...">
                    Xác nhận ngắt
                  </LoadingButton>
                  <button type="button" className="btn-quiet" onClick={() => setDisconnectId("")}>
                    Hủy
                  </button>
                </form>
              )}
            </article>
          ))}
        </section>
      )}
    </Shell>
  );
}
