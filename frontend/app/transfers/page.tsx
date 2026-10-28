"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { Shell } from "@/components/Shell";
import { Feedback } from "@/components/Feedback";
import { Icon } from "@/components/Icon";
import { LoadingButton } from "@/components/LoadingButton";
import { useSession } from "@/components/SessionProvider";
import { api, formatMoney, session } from "@/lib/api";
import { useApiQuery } from "@/lib/useApiQuery";
import { requestKey } from "@/lib/requestKey";
import { operationTone, transferLabels, liveTransferLabels } from "@/lib/operations";
import type { Organization, Payment, Transfer } from "@/types";

type Capabilities = { mode: string; real_money_enabled: boolean; safety_limit: number };

export default function TransfersPage() {
  const { user } = useSession();
  const [organizationId, setOrganizationId] = useState("");
  const [selected, setSelected] = useState("");
  const [key, setKey] = useState(requestKey);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [totp, setTotp] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  useEffect(() => {
    setOrganizationId(session().organizationId);
    setSelected(new URLSearchParams(window.location.search).get("payment") || "");
  }, []);
  const role = user?.organizations.find((item) => item.id === organizationId)?.role;
  const canManage = role === "OWNER" || role === "APPROVER";
  const history = useApiQuery<Transfer[]>(organizationId ? "/transfers" : null);
  const payments = useApiQuery<Payment[]>(organizationId ? "/payment-requests" : null);
  const organization = useApiQuery<Organization>(
    organizationId ? "/organizations/" + organizationId : null,
  );
  const capabilities = useApiQuery<Capabilities>(organizationId ? "/transfers/capabilities" : null);
  const eligible = (payments.data || []).filter(
    (item) =>
      item.status === "SIGNED" &&
      new Date(item.expires_at) > new Date() &&
      !(history.data || []).some(
        (transfer) =>
          transfer.payment_request_id === item.id &&
          transfer.payment_version === item.current_version,
      ),
  );
  const payment = eligible.find((item) => item.id === selected);
  const verified = organization.data?.verification_status === "APPROVED";
  const sandbox = capabilities.data?.mode === "sandbox";
  const live = Boolean(capabilities.data?.real_money_enabled);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !payment) return;
    setBusy("create");
    setError("");
    setNotice("");
    try {
      const result = await api<Transfer>("/transfers", {
        method: "POST",
        headers: { "Idempotency-Key": key },
        body: JSON.stringify({
          payment_request_id: payment.id,
          totp_code: totp,
          confirm_live: live && confirmed,
        }),
      });
      setSelected("");
      setKey(requestKey());
      setTotp("");
      setConfirmed(false);
      await history.reload();
      setNotice(
        result.provider === "payos"
          ? liveTransferLabels[result.status] || "Đã lưu lệnh chi. Hãy đối soát với payOS."
          : "Đã tạo lệnh chuyển thử nghiệm. Chưa có tiền thật được chuyển; hãy mô phỏng kết quả hoặc đối soát.",
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không thể tạo lệnh.");
    } finally {
      setBusy("");
    }
  }

  async function process(item: Transfer, action: "reconcile" | "SUCCEEDED" | "FAILED" | "DELAYED") {
    if (busy) return;
    setBusy(item.id);
    setError("");
    setNotice("");
    try {
      await api(
        "/transfers/" + item.id + "/" + (action === "reconcile" ? "reconcile" : "sandbox-outcome"),
        {
          method: "POST",
          ...(action !== "reconcile"
            ? {
                body: JSON.stringify({
                  status: action === "DELAYED" ? "SUCCEEDED" : action,
                  deliver_event: action !== "DELAYED",
                }),
              }
            : {}),
        },
      );
      await history.reload();
      setNotice(
        action === "DELAYED"
          ? "Nhà cung cấp thử nghiệm đã ghi nhận thành công nhưng chưa gửi thông báo. Bấm Đối soát để lấy kết quả."
          : action === "reconcile"
            ? item.provider === "payos"
              ? "Đã lấy kết quả lệnh chi trực tiếp từ payOS."
              : "Đã đối soát với sổ giao dịch của nhà cung cấp thử nghiệm."
            : "Đã ghi nhận kết quả mô phỏng. Không có tiền thật được chuyển.",
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không thể xử lý giao dịch.");
    } finally {
      setBusy("");
    }
  }

  async function dispatchQueued(event: FormEvent<HTMLFormElement>, item: Transfer) {
    event.preventDefault();
    if (busy) return;
    const data = new FormData(event.currentTarget);
    setBusy(item.id);
    setError("");
    setNotice("");
    try {
      const result = await api<Transfer>("/transfers/" + item.id + "/dispatch", {
        method: "POST",
        body: JSON.stringify({
          confirm_live: data.get("confirmed") === "on",
          totp_code: data.get("totp"),
        }),
      });
      await history.reload();
      setNotice(liveTransferLabels[result.status] || "Đã xử lý lệnh đã lưu.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Chưa gửi được lệnh đã lưu.");
    } finally {
      setBusy("");
    }
  }

  return (
    <Shell
      title={sandbox ? "Chuyển tiền thử nghiệm" : "Chi tiền"}
      description="Từ yêu cầu đã ký đến lệnh chi, kết quả nhà cung cấp và đối soát."
      action={
        <Link href="/settings/payments" className="btn-secondary">
          Kết nối thanh toán
        </Link>
      }
    >
      <div className="mb-5 rounded-2xl border border-amber-200 bg-amber-50 p-5">
        <div className="flex items-start gap-3">
          <Icon name="alert" className="shrink-0 text-amber-700" />
          <div>
            <h2 className="font-bold text-amber-950">
              {live
                ? "TIỀN THẬT · Kiểm tra kỹ trước khi xác nhận"
                : sandbox
                  ? "SANDBOX · Không chuyển tiền thật"
                  : "CHƯA BẬT CHI TIỀN THẬT"}
            </h2>
            <p className="mt-1 text-sm leading-relaxed text-amber-900">
              {live
                ? "Lệnh mới có thể chi tiền từ kênh payOS đã kết nối. Mã MFA và xác nhận bên dưới cho phép gửi đúng một lệnh; mất kết nối phải đối soát, không tự gửi lại."
                : "Kênh chi thật chưa được bật. Lệnh sandbox chỉ phục vụ thử nghiệm. Xem Kết nối thanh toán để hoàn tất tài khoản, quyền dịch vụ và hạ tầng."}
            </p>
          </div>
        </div>
      </div>
      <Feedback
        loading={
          history.loading || payments.loading || organization.loading || capabilities.loading
        }
        error={history.error || payments.error || organization.error || capabilities.error}
        retry={() => {
          void history.reload();
          void payments.reload();
          void organization.reload();
          void capabilities.reload();
        }}
      />
      {error && (
        <div className="alert-error mb-5" role="alert">
          <Icon name="alert" />
          <span>{error}</span>
        </div>
      )}
      {notice && (
        <div className="alert-success mb-5" role="status">
          <Icon name="check" />
          <span>{notice}</span>
        </div>
      )}
      {!verified && organization.data && (
        <section className="card mb-5">
          <h2 className="section-title">Cần hoàn tất xác minh doanh nghiệp</h2>
          <p className="muted mt-2">
            Chỉ hồ sơ đã được xét duyệt độc lập và còn hiệu lực mới tạo được lệnh. Tổ chức demo
            không tự động được cấp quyền này.
          </p>
          <Link href="/organization/verification" className="btn-secondary mt-4">
            Xem hồ sơ xác minh
            <Icon name="arrowRight" size={17} />
          </Link>
        </section>
      )}
      {capabilities.data && !sandbox && !live && (
        <div className="alert-error mb-5" role="alert">
          Chưa đủ điều kiện chi tiền thật. Hãy hoàn tất các bước trong mục Kết nối thanh toán.
        </div>
      )}
      {canManage && verified && (sandbox || live) && (
        <form onSubmit={create} className="card mb-5">
          <h2 className="section-title">
            {live ? "Tạo lệnh chi tiền thật" : "Tạo lệnh thử nghiệm"}
          </h2>
          <p className="muted mt-2">
            Thông tin tiền và người nhận lấy từ nội dung đã ký, không nhập lại tài khoản. Người tạo
            yêu cầu không được tự tạo lệnh chuyển.
          </p>
          {live && (
            <p className="hint mt-3">
              Hạn mức mỗi lệnh: {formatMoney(capabilities.data?.safety_limit || 0, "VND")}. Chỉ dùng
              mã BIN ngân hàng 6 số trên yêu cầu đã ký.
            </p>
          )}
          {!user?.mfa_enabled && (
            <p className="mt-4 rounded-xl bg-amber-50 p-3 text-sm text-amber-900">
              Cần{" "}
              <Link href="/settings/security" className="font-semibold underline">
                bật xác thực hai bước
              </Link>{" "}
              trước khi tạo lệnh.
            </p>
          )}
          <fieldset disabled={Boolean(busy)} className="mt-5 space-y-4">
            <label>
              <span id="transfer-payment-label" className="label">
                Yêu cầu đã ký
              </span>
              <select
                aria-labelledby="transfer-payment-label"
                required
                value={payment?.id || ""}
                onChange={(event) => {
                  setSelected(event.target.value);
                  setKey(requestKey());
                  setTotp("");
                  setConfirmed(false);
                }}
              >
                <option value="">Chọn yêu cầu còn hiệu lực...</option>
                {eligible.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.invoice_reference} · {formatMoney(item.amount_minor, item.currency)}
                  </option>
                ))}
              </select>
            </label>
            {eligible.length === 0 && (
              <p className="muted">
                Chưa có yêu cầu đủ điều kiện hoặc các yêu cầu đã có lệnh chuyển.{" "}
                <Link href="/payment-requests" className="text-teal-700 underline">
                  Xem yêu cầu thanh toán
                </Link>
              </p>
            )}
            {payment && (
              <div className="surface-muted p-4">
                <p className="text-2xl font-bold text-slate-900">
                  {formatMoney(payment.amount_minor, payment.currency)}
                </p>
                <p className="mt-2 text-sm text-slate-600">
                  {payment.beneficiary_name} · {payment.bank_code} · {payment.account_masked}
                </p>
              </div>
            )}
            <label>
              <span className="label">Mã xác thực 6 số</span>
              <input
                value={totp}
                onChange={(event) => setTotp(event.target.value.replace(/\D/g, "").slice(0, 6))}
                required
                pattern="[0-9]{6}"
                inputMode="numeric"
                autoComplete="one-time-code"
                placeholder="000000"
                className="max-w-xs"
              />
            </label>
            {live && (
              <label className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4">
                <input
                  type="checkbox"
                  checked={confirmed}
                  onChange={(event) => setConfirmed(event.target.checked)}
                  required
                  className="mt-1 size-4"
                />
                <span className="text-sm leading-relaxed text-amber-950">
                  Tôi đã kiểm tra số tiền, người nhận và tài khoản nguồn. Tôi xác nhận gửi lệnh chi
                  tiền thật qua payOS cho yêu cầu đang chọn.
                </span>
              </label>
            )}
            <LoadingButton
              busy={busy === "create"}
              busyLabel="Đang tạo lệnh..."
              disabled={!payment || !user?.mfa_enabled || totp.length !== 6 || (live && !confirmed)}
            >
              {live ? "Xác nhận chi tiền thật" : "Xác nhận tạo lệnh thử nghiệm"}
              <Icon name="arrowRight" size={17} />
            </LoadingButton>
          </fieldset>
        </form>
      )}
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="section-title">Lịch sử lệnh chi</h2>
        <button
          type="button"
          className="btn-secondary"
          disabled={Boolean(busy) || history.loading}
          onClick={() => history.reload()}
        >
          Tải lại
          <Icon name="history" size={16} />
        </button>
      </div>
      {!history.loading && history.data?.length === 0 && (
        <section className="card py-10 text-center">
          <Icon name="wallet" size={32} className="mx-auto text-teal-700" />
          <h3 className="section-title mt-3">Chưa có lệnh chi</h3>
          <p className="muted mt-2">Hoàn tất xác minh doanh nghiệp và ký yêu cầu để bắt đầu.</p>
        </section>
      )}
      <div className="space-y-4">
        {history.data?.map((item) => (
          <section className="card" key={item.id}>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <Link
                  href={"/payment-requests/" + item.payment_request_id}
                  className="font-semibold text-teal-700 hover:underline"
                >
                  {item.invoice_reference}
                </Link>
                <p className="mt-2 text-2xl font-bold tracking-tight text-slate-900">
                  {formatMoney(item.amount_minor, item.currency)}
                </p>
                <p className="muted mt-2">
                  {item.beneficiary_name} · {item.bank_code} · ******{item.account_last4}
                </p>
              </div>
              <span className={"badge " + operationTone(item.status)}>
                {(item.provider === "payos"
                  ? liveTransferLabels[item.status]
                  : transferLabels[item.status]) || item.status}
              </span>
            </div>
            <p className="hint mt-4 break-all">
              {item.provider === "payos" ? "payOS · TIỀN THẬT" : "Sandbox · THỬ NGHIỆM"} · Mã tham
              chiếu: {item.provider_reference}
            </p>
            <p className="hint">
              Tạo lúc {new Date(item.created_at).toLocaleString("vi-VN")}
              {item.reconciled_at &&
                " · Đối soát lúc " + new Date(item.reconciled_at).toLocaleString("vi-VN")}
            </p>
            {item.status === "FAILED" && (
              <p className="mt-3 text-sm text-red-700">
                Lệnh báo thất bại. Không tự chuyển lại yêu cầu này để tránh tạo giao dịch trùng.
              </p>
            )}
            {item.provider === "payos" && ["UNKNOWN", "DISPATCHING"].includes(item.status) && (
              <p className="mt-3 rounded-xl bg-amber-50 p-3 text-sm text-amber-900">
                Chưa rõ tiền đã được chuyển hay chưa. Chỉ đối soát; không gửi lại hoặc tạo lệnh thay
                thế.
              </p>
            )}
            {canManage && live && item.provider === "payos" && item.status === "QUEUED" && (
              <form
                onSubmit={(event) => dispatchQueued(event, item)}
                className="mt-4 space-y-3 rounded-xl border border-amber-200 p-4"
              >
                <p className="text-sm text-slate-700">
                  Lệnh đã lưu nhưng chưa gửi. Kiểm tra thông tin ở trên trước khi xác nhận.
                </p>
                <label>
                  <span className="label">Mã MFA để gửi lệnh đã lưu</span>
                  <input
                    name="totp"
                    required
                    pattern="[0-9]{6}"
                    inputMode="numeric"
                    maxLength={6}
                    autoComplete="one-time-code"
                    className="max-w-xs"
                  />
                </label>
                <label className="flex items-start gap-3">
                  <input name="confirmed" type="checkbox" required className="mt-1 size-4" />
                  <span className="text-sm text-slate-700">
                    Tôi xác nhận chi tiền thật cho đúng lệnh đã lưu này.
                  </span>
                </label>
                <LoadingButton busy={busy === item.id} busyLabel="Đang gửi...">
                  Xác nhận gửi lệnh đã lưu
                </LoadingButton>
              </form>
            )}
            {canManage && (
              <div className="mt-4 flex flex-wrap gap-2">
                {item.provider === "sandbox" && sandbox && item.status === "SUBMITTED" && (
                  <>
                    <button
                      type="button"
                      className="btn-secondary"
                      disabled={Boolean(busy)}
                      onClick={() => process(item, "SUCCEEDED")}
                    >
                      Mô phỏng thành công
                    </button>
                    <button
                      type="button"
                      className="btn-secondary"
                      disabled={Boolean(busy)}
                      onClick={() => process(item, "FAILED")}
                    >
                      Mô phỏng thất bại
                    </button>
                    <button
                      type="button"
                      className="btn-quiet"
                      disabled={Boolean(busy)}
                      onClick={() => process(item, "DELAYED")}
                    >
                      Mô phỏng mất thông báo
                    </button>
                  </>
                )}
                <LoadingButton
                  type="button"
                  busy={busy === item.id}
                  busyLabel="Đang xử lý..."
                  className="btn-primary"
                  disabled={Boolean(busy) && busy !== item.id}
                  onClick={() => process(item, "reconcile")}
                >
                  Đối soát
                  <Icon name="history" size={16} />
                </LoadingButton>
              </div>
            )}
          </section>
        ))}
      </div>
    </Shell>
  );
}
