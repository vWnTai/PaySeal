"use client";

import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";
import { Shell } from "@/components/Shell";
import { Icon } from "@/components/Icon";
import { Feedback } from "@/components/Feedback";
import { LoadingButton } from "@/components/LoadingButton";
import { useSession } from "@/components/SessionProvider";
import { api, formatMoney, session } from "@/lib/api";
import { useApiQuery } from "@/lib/useApiQuery";
import { requestKey } from "@/lib/requestKey";
import { localDateTime, toMinorUnits } from "@/lib/payment";
import { collectionLabels, operationTone } from "@/lib/operations";
import type { Collection, PaymentReadiness } from "@/types";

export default function CollectionsPage() {
  const { user } = useSession();
  const [organizationId, setOrganizationId] = useState("");
  const [key, setKey] = useState(requestKey);
  const [amount, setAmount] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [expiry, setExpiry] = useState("");
  const createForm = useRef<HTMLFormElement>(null);
  useEffect(() => {
    setOrganizationId(session().organizationId);
    setExpiry(localDateTime(new Date(Date.now() + 24 * 3600 * 1000)));
  }, []);
  const role = user?.organizations.find((item) => item.id === organizationId)?.role;
  const canReconcile = role === "OWNER" || role === "APPROVER";
  const history = useApiQuery<Collection[]>(organizationId ? "/collections" : null);
  const readiness = useApiQuery<PaymentReadiness>(
    organizationId ? "/payment-integrations/status" : null,
  );
  const enabled =
    readiness.data?.infrastructure_ready &&
    readiness.data.business_verified &&
    readiness.data.collection_connected;
  let preview = "";
  try {
    preview = formatMoney(toMinorUnits(amount, "VND"), "VND");
  } catch {
    /* Wait for valid input. */
  }

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || submitted) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    setBusy("create");
    setError("");
    setNotice("");
    try {
      const result = await api<Collection>("/collections", {
        method: "POST",
        headers: { "Idempotency-Key": key },
        body: JSON.stringify({
          invoice_reference: data.get("reference"),
          amount_minor: toMinorUnits(String(data.get("amount")), "VND"),
          expires_at: new Date(String(data.get("expires"))).toISOString(),
          totp_code: data.get("totp"),
        }),
      });
      setSubmitted(true);
      await history.reload();
      setNotice(
        result.status === "UNKNOWN"
          ? "Đã lưu khoản thu nhưng chưa rõ kết quả từ payOS. Đối soát khoản này, không tạo liên kết thay thế."
          : "Đã tạo liên kết thu tiền. Chỉ ghi nhận đã thu sau khi đối soát kết quả từ payOS.",
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không thể tạo khoản thu.");
      await history.reload();
    } finally {
      setBusy("");
    }
  }

  async function reconcile(item: Collection) {
    if (busy) return;
    setBusy(item.id);
    setError("");
    setNotice("");
    try {
      await api("/collections/" + item.id + "/reconcile", { method: "POST" });
      await history.reload();
      setNotice(
        "Đã lấy trạng thái và số tiền nhận tích lũy từ payOS. Không cộng tiền từ tham số chuyển hướng trên trình duyệt.",
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Chưa đối soát được khoản thu.");
    } finally {
      setBusy("");
    }
  }

  return (
    <Shell
      title="Thu tiền"
      description="Tạo liên kết thanh toán cho khách, nhận tiền về kênh của tổ chức và theo dõi kết quả đối soát."
      action={
        <Link href="/settings/payments" className="btn-secondary">
          <Icon name="building" size={17} />
          Kết nối thanh toán
        </Link>
      }
    >
      <Feedback
        loading={history.loading || readiness.loading}
        error={history.error || readiness.error}
        retry={() => {
          void history.reload();
          void readiness.reload();
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
      {!enabled && readiness.data && (
        <section className="card mb-6 border-teal-200 bg-teal-50/50">
          <Icon name="wallet" size={32} className="text-teal-700" />
          <h2 className="mt-4 text-xl font-bold text-slate-900">Chuẩn bị kênh thu đầu tiên</h2>
          <p className="muted mt-2 max-w-2xl">
            Bạn chưa kết nối kênh thu đủ điều kiện. Hãy hoàn thiện hồ sơ, bật bảo mật và làm theo
            hướng dẫn kết nối payOS. Màn hình này chưa tạo giao dịch tiền thật.
          </p>
          <Link href="/settings/payments" className="btn-primary mt-5">
            Xem các bước cần làm <Icon name="arrowRight" size={17} />
          </Link>
        </section>
      )}
      {enabled && role === "OWNER" && (
        <form ref={createForm} onSubmit={create} className="card mb-6 max-w-3xl">
          <h2 className="section-title">Tạo liên kết nhận tiền</h2>
          <p className="muted mt-2">
            Tiền nhận về tài khoản đã kết nối của tổ chức. Khoản thu này độc lập với yêu cầu chi
            tiền đã ký.
          </p>
          <fieldset
            disabled={Boolean(busy) || submitted}
            className="mt-5 grid gap-4 sm:grid-cols-2"
          >
            <label className="sm:col-span-2">
              <span className="label">Mã hóa đơn / nội dung khoản thu</span>
              <input name="reference" required maxLength={160} placeholder="VD: HD-2026-001" />
            </label>
            <label>
              <span className="label">Số tiền (VND)</span>
              <input
                name="amount"
                required
                inputMode="decimal"
                value={amount}
                onChange={(event) => setAmount(event.target.value)}
                placeholder="200000"
              />
              <span className="hint">
                {preview || "Nhập số tiền nguyên đồng, không dùng dấu phân cách hàng nghìn."}
              </span>
            </label>
            <label>
              <span className="label">Hiệu lực đến</span>
              <input
                name="expires"
                type="datetime-local"
                required
                value={expiry}
                onChange={(event) => setExpiry(event.target.value)}
              />
              <span className="hint">Tối đa 7 ngày kể từ lúc tạo.</span>
            </label>
            <label>
              <span className="label">Mã xác thực 6 số</span>
              <input
                name="totp"
                required
                inputMode="numeric"
                pattern="[0-9]{6}"
                maxLength={6}
                autoComplete="one-time-code"
              />
            </label>
            <div className="sm:col-span-2">
              <LoadingButton
                busy={busy === "create"}
                busyLabel="Đang tạo liên kết..."
                disabled={!user?.mfa_enabled}
              >
                Tạo liên kết thu tiền
              </LoadingButton>
            </div>
          </fieldset>
          {submitted && (
            <button
              type="button"
              className="btn-secondary mt-4"
              onClick={() => {
                setSubmitted(false);
                setKey(requestKey());
                setAmount("");
                createForm.current?.reset();
                setExpiry(localDateTime(new Date(Date.now() + 24 * 3600 * 1000)));
              }}
            >
              Tạo khoản thu khác
            </button>
          )}
        </form>
      )}
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="section-title">Các khoản thu</h2>
        <button
          type="button"
          className="btn-secondary"
          disabled={Boolean(busy) || history.loading}
          onClick={() => history.reload()}
        >
          Tải lại <Icon name="history" size={16} />
        </button>
      </div>
      {history.data?.length === 0 && (
        <section className="card py-10 text-center">
          <Icon name="file" size={30} className="mx-auto text-slate-400" />
          <h3 className="section-title mt-3">Chưa có khoản thu</h3>
          <p className="muted mt-2">
            Khi kênh đã kết nối, bạn có thể tạo liên kết và gửi cho khách thanh toán.
          </p>
        </section>
      )}
      <div className="space-y-4">
        {history.data?.map((item) => (
          <article className="card" key={item.id}>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <h3 className="font-semibold text-slate-900">{item.invoice_reference}</h3>
                <p className="mt-2 text-2xl font-bold tracking-tight">
                  {formatMoney(item.amount_minor, "VND")}
                </p>
                <p className="muted mt-2">
                  Đã nhận theo đối soát: {formatMoney(item.amount_paid, "VND")}
                </p>
              </div>
              <span
                className={
                  "badge " + operationTone(item.status === "PAID" ? "SUCCEEDED" : item.status)
                }
              >
                {collectionLabels[item.status] || item.status}
              </span>
            </div>
            <p className="hint mt-4 break-all">
              Mã đơn: {item.order_code} · Hết hạn:{" "}
              {new Date(item.expires_at).toLocaleString("vi-VN")}
            </p>
            {item.status === "UNKNOWN" && (
              <p className="mt-3 text-sm text-amber-800">
                Chưa rõ nhà cung cấp đã tạo liên kết hay chưa. Không tạo lại khoản này trước khi đối
                soát.
              </p>
            )}
            <div className="mt-4 flex flex-wrap gap-3">
              {item.checkout_url &&
                !["PAID", "CANCELLED", "EXPIRED", "FAILED"].includes(item.status) && (
                  <>
                    <a
                      href={item.checkout_url}
                      className="btn-primary"
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      Mở trang thanh toán payOS <Icon name="arrowRight" size={16} />
                    </a>
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={async () => {
                        try {
                          await navigator.clipboard.writeText(item.checkout_url!);
                          setNotice("Đã sao chép liên kết thanh toán.");
                        } catch {
                          setError(
                            "Trình duyệt không cho sao chép. Hãy mở trang payOS và sao chép địa chỉ.",
                          );
                        }
                      }}
                    >
                      Sao chép liên kết
                    </button>
                  </>
                )}
              {canReconcile && (
                <LoadingButton
                  type="button"
                  busy={busy === item.id}
                  busyLabel="Đang đối soát..."
                  className="btn-secondary"
                  disabled={Boolean(busy) && busy !== item.id}
                  onClick={() => reconcile(item)}
                >
                  Đối soát với payOS <Icon name="history" size={16} />
                </LoadingButton>
              )}
            </div>
          </article>
        ))}
      </div>
    </Shell>
  );
}
