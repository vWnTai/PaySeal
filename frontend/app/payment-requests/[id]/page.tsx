"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { FormEvent, useState } from "react";
import { Shell } from "@/components/Shell";
import { Feedback } from "@/components/Feedback";
import { StatusBadge } from "@/components/StatusBadge";
import { Icon } from "@/components/Icon";
import { api, apiRequest, formatMoney } from "@/lib/api";
import { useApiQuery } from "@/lib/useApiQuery";
import { requestKey } from "@/lib/requestKey";
import { LoadingButton } from "@/components/LoadingButton";
import { PaymentProgress } from "@/components/PaymentProgress";
import type { Payment } from "@/types";

type Action = "submit" | "approve" | "reject" | "sign" | "revoke";
const actionLabels: Record<Action, string> = {
  submit: "Gửi phê duyệt",
  approve: "Phê duyệt",
  reject: "Từ chối",
  sign: "Ký và tạo PDF",
  revoke: "Thu hồi yêu cầu",
};

export default function PaymentDetail() {
  const { id } = useParams<{ id: string }>();
  const {
    data: item,
    error: loadError,
    loading,
    reload: load,
  } = useApiQuery<Payment>("/payment-requests/" + id);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [chosenAction, setChosenAction] = useState<Action | null>(null);
  const [totp, setTotp] = useState("");
  const [comment, setComment] = useState("");
  const [downloading, setDownloading] = useState(false);
  const [signKey] = useState(requestKey);

  async function execute(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!chosenAction) return;
    setBusy(true);
    setError("");
    setNotice("");
    const action = chosenAction;
    try {
      const body =
        action === "revoke"
          ? { reason: comment.trim() }
          : { totp_code: totp || null, comment: comment.trim() || null };
      await api("/payment-requests/" + id + "/" + action, {
        method: "POST",
        headers: action === "sign" ? { "Idempotency-Key": signKey } : {},
        body: JSON.stringify(body),
      });
      setChosenAction(null);
      setTotp("");
      setComment("");
      await load();
      setNotice(actionLabels[action] + " thành công.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không thể thực hiện thao tác");
    } finally {
      setBusy(false);
    }
  }

  async function downloadPdf() {
    setError("");
    setDownloading(true);
    try {
      const response = await apiRequest("/payment-requests/" + id + "/pdf");
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = "payseal-" + id + ".pdf";
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không thể tải PDF");
    } finally {
      setDownloading(false);
    }
  }

  async function copyUrl() {
    if (!item?.public_url) return;
    try {
      await navigator.clipboard.writeText(item.public_url);
      setNotice("Đã sao chép liên kết xác minh.");
    } catch {
      setError("Không thể sao chép tự động. Hãy chọn và sao chép liên kết bên dưới.");
    }
  }

  if (!item)
    return (
      <Shell title="Chi tiết yêu cầu">
        <Feedback loading={loading} error={loadError || error} retry={load} />
      </Shell>
    );
  const isLocalUrl =
    item.public_url && /https?:\/\/(localhost|127\.0\.0\.1)(:|\/|$)/i.test(item.public_url);
  const actions: Action[] =
    item.status === "DRAFT"
      ? ["submit"]
      : item.status === "PENDING_APPROVAL"
        ? ["approve", "reject"]
        : item.status === "APPROVED"
          ? ["sign"]
          : item.status === "SIGNED"
            ? ["revoke"]
            : [];
  return (
    <Shell
      title={item.invoice_reference}
      description="Kiểm tra thông tin và trạng thái của yêu cầu thanh toán."
      action={
        <Link href="/payment-requests" className="btn-secondary w-full sm:w-auto">
          <Icon name="arrowLeft" size={17} />
          Danh sách
        </Link>
      }
    >
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <StatusBadge status={item.status} />
        <span className="text-sm text-slate-500">
          Tạo ngày {new Date(item.created_at).toLocaleString("vi-VN")}
        </span>
      </div>
      <PaymentProgress status={item.status} />
      {(error || loadError) && (
        <div role="alert" className="alert-error mb-5">
          <Icon name="alert" size={20} />
          <span>{error || loadError}</span>
        </div>
      )}
      {notice && (
        <div role="status" className="alert-success mb-5">
          <Icon name="check" size={20} />
          <span>{notice}</span>
        </div>
      )}
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_330px]">
        <div className="space-y-5">
          <section className="card">
            <h2 className="section-title">Chi tiết thanh toán</h2>
            <dl className="mt-5 grid gap-5 sm:grid-cols-2">
              <Info label="Số tiền" value={formatMoney(item.amount_minor, item.currency)} strong />
              <Info label="Người thụ hưởng" value={item.beneficiary_name} />
              <Info
                label="Ngân hàng / tài khoản"
                value={item.bank_code + " · " + item.account_masked}
              />
              <Info
                label="Hết hiệu lực"
                value={new Date(item.expires_at).toLocaleString("vi-VN")}
              />
              <Info
                label="Đã phê duyệt"
                value={item.approvals_completed + " / " + item.approvals_required}
              />
              <Info label="Mã yêu cầu" value={item.id} />
            </dl>
          </section>
          {item.public_url && (
            <section className="card">
              <div className="flex items-center gap-2">
                <span className="grid h-9 w-9 place-items-center rounded-lg bg-teal-50 text-teal-700">
                  <Icon name="shield" size={20} />
                </span>
                <h2 className="section-title">Xác minh công khai</h2>
              </div>
              <p className="muted mt-3">
                Gửi liên kết này cùng PDF để người nhận kiểm tra trạng thái yêu cầu.
              </p>
              <div className="mt-4 break-all rounded-xl bg-slate-50 p-3 text-sm text-teal-800">
                {item.public_url}
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <button type="button" className="btn-secondary" onClick={copyUrl}>
                  <Icon name="copy" size={17} />
                  Sao chép
                </button>
                <a
                  className="btn-secondary"
                  href={item.public_url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <Icon name="external" size={17} />
                  Mở trang xác minh
                </a>
              </div>
              {isLocalUrl && (
                <p className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                  <strong>QR chưa mở được trên điện thoại?</strong> Liên kết đang dùng localhost —
                  địa chỉ này chỉ chạy trên máy tính đang mở ứng dụng. Cần đổi địa chỉ xác minh sang
                  tên miền công khai rồi tạo lại PDF.
                </p>
              )}
            </section>
          )}
        </div>
        <aside className="card h-fit">
          <h2 className="section-title">Bước tiếp theo</h2>
          <p className="muted mt-1">
            {item.status === "DRAFT"
              ? "Gửi yêu cầu để bắt đầu phê duyệt."
              : item.status === "PENDING_APPROVAL"
                ? "Xem kỹ số tiền và người nhận trước khi quyết định."
                : item.status === "APPROVED"
                  ? "Ký yêu cầu để phát hành PDF có thể xác minh."
                  : item.status === "SIGNED"
                    ? "Tải PDF và chia sẻ cùng liên kết xác minh."
                    : "Yêu cầu này không còn thao tác tiếp theo."}
          </p>
          {item.status === "SIGNED" && (
            <div className="mt-5 space-y-3">
              <Link href={"/transfers?payment=" + item.id} className="btn-secondary w-full">
                Chuyển tiền thử nghiệm <Icon name="arrowRight" size={17} />
              </Link>
              <LoadingButton
                type="button"
                busy={downloading}
                busyLabel="Đang tải PDF..."
                className="btn-primary w-full"
                onClick={downloadPdf}
              >
                <Icon name="download" size={18} />
                Tải PDF
              </LoadingButton>
            </div>
          )}
          {actions.length > 0 && (
            <div className="mt-5 space-y-2">
              {actions.map((action) => (
                <button
                  type="button"
                  key={action}
                  disabled={busy}
                  className={
                    (action === "reject" || action === "revoke" ? "btn-secondary" : "btn-primary") +
                    " w-full"
                  }
                  onClick={() => {
                    setChosenAction(action);
                    setError("");
                    setComment("");
                    setTotp("");
                  }}
                >
                  {actionLabels[action]}
                </button>
              ))}
            </div>
          )}
          {chosenAction && (
            <form
              onSubmit={execute}
              className="page-enter mt-5 space-y-4 rounded-xl border border-slate-200 bg-slate-50 p-4"
            >
              <h3 className="font-semibold text-slate-900">
                Xác nhận: {actionLabels[chosenAction]}
              </h3>
              {item.recent_mfa_required &&
                (chosenAction === "approve" || chosenAction === "sign") && (
                  <label>
                    <span className="label">Mã xác thực 6 số</span>
                    <input
                      value={totp}
                      onChange={(e) => setTotp(e.target.value)}
                      required
                      maxLength={6}
                      autoFocus
                      pattern="[0-9]{6}"
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      placeholder="000000"
                    />
                  </label>
                )}
              {(chosenAction === "reject" || chosenAction === "revoke") && (
                <label>
                  <span className="label">
                    Lý do {chosenAction === "revoke" && <span className="text-red-600">*</span>}
                  </span>
                  <textarea
                    value={comment}
                    onChange={(e) => setComment(e.target.value)}
                    required={chosenAction === "revoke"}
                    rows={3}
                    maxLength={500}
                    minLength={chosenAction === "revoke" ? 3 : undefined}
                    autoFocus
                    placeholder="Nhập lý do để ghi nhận..."
                  />
                </label>
              )}
              <div className="flex flex-col gap-2">
                <LoadingButton
                  busy={busy}
                  busyLabel="Đang xử lý..."
                  className={chosenAction === "revoke" ? "btn-danger" : "btn-primary"}
                >
                  Xác nhận
                </LoadingButton>
                <button
                  type="button"
                  disabled={busy}
                  className="btn-quiet"
                  onClick={() => setChosenAction(null)}
                >
                  Hủy
                </button>
              </div>
            </form>
          )}
        </aside>
      </div>
    </Shell>
  );
}

function Info({
  label,
  value,
  strong = false,
}: {
  label: string;
  value: string;
  strong?: boolean;
}) {
  return (
    <div>
      <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</dt>
      <dd
        className={
          "mt-1 break-words font-semibold text-slate-900 " +
          (strong ? "text-2xl tracking-tight" : "text-sm")
        }
      >
        {value}
      </dd>
    </div>
  );
}
