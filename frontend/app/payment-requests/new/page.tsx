"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { Shell } from "@/components/Shell";
import { Feedback } from "@/components/Feedback";
import { Icon } from "@/components/Icon";
import { api, formatMoney } from "@/lib/api";
import { useApiQuery } from "@/lib/useApiQuery";
import { localDateTime, toMinorUnits } from "@/lib/payment";
import { LoadingButton } from "@/components/LoadingButton";
import { requestKey } from "@/lib/requestKey";
import type { Beneficiary, Payment } from "@/types";

function defaultExpiry() {
  return localDateTime(new Date(Date.now() + 24 * 60 * 60 * 1000));
}

export default function NewPayment() {
  const router = useRouter();
  const { data, error: loadError, loading, reload } = useApiQuery<Beneficiary[]>("/beneficiaries");
  const beneficiaries = data || [];
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [currency, setCurrency] = useState("VND");
  const [beneficiaryId, setBeneficiaryId] = useState("");
  const [amount, setAmount] = useState("");
  const [idempotencyKey] = useState(requestKey);
  let amountPreview = "";
  try {
    amountPreview = formatMoney(toMinorUnits(amount, currency), currency);
  } catch {
    /* Preview appears once the amount is valid. */
  }
  const chosen = beneficiaries.find((b) => b.id === beneficiaryId);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(event.currentTarget);
    try {
      const payment = await api<Payment>("/payment-requests", {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify({
          invoice_reference: String(data.get("invoice")).trim(),
          amount_minor: toMinorUnits(String(data.get("amount")), currency),
          currency,
          beneficiary_id: beneficiaryId,
          expires_at: new Date(String(data.get("expires"))).toISOString(),
          note: data.get("note") || null,
        }),
      });
      router.push("/payment-requests/" + payment.id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không thể tạo yêu cầu");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Shell
      title="Tạo yêu cầu thanh toán"
      description="Điền thông tin, kiểm tra lại người nhận rồi lưu bản nháp. Bạn có thể gửi phê duyệt ở bước tiếp theo."
      action={
        <Link href="/payment-requests" className="btn-secondary w-full sm:w-auto">
          <Icon name="arrowLeft" size={17} />
          Quay lại
        </Link>
      }
    >
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div>
          <Feedback loading={loading} error={loadError} retry={reload} />
          {!loading && !loadError && beneficiaries.length === 0 && (
            <div className="card mb-5">
              <h2 className="section-title">Chưa có người thụ hưởng</h2>
              <p className="muted mt-1">Cần thêm người nhận trước khi tạo yêu cầu.</p>
              <Link href="/beneficiaries/new" className="btn-primary mt-4">
                Thêm người thụ hưởng <Icon name="arrowRight" size={17} />
              </Link>
            </div>
          )}
          {!loading && !loadError && beneficiaries.length > 0 && (
            <form onSubmit={submit} className="card space-y-6">
              {error && (
                <div role="alert" className="alert-error">
                  <Icon name="alert" size={20} />
                  <span>{error}</span>
                </div>
              )}
              <div>
                <p className="eyebrow">Bước 1 / 2</p>
                <h2 className="section-title mt-1">Thông tin thanh toán</h2>
                <p className="muted mt-1">
                  Các thông tin này sẽ xuất hiện trong tài liệu xác nhận.
                </p>
              </div>
              <div className="grid gap-5 sm:grid-cols-2">
                <label className="sm:col-span-2">
                  <span className="label">
                    Mã hóa đơn <span className="text-red-600">*</span>
                  </span>
                  <input name="invoice" required maxLength={128} placeholder="Ví dụ: HD-2026-001" />
                  <span className="hint">Dùng mã duy nhất để dễ tra cứu.</span>
                </label>
                <label>
                  <span className="label">
                    Số tiền <span className="text-red-600">*</span>
                  </span>
                  <input
                    name="amount"
                    value={amount}
                    onChange={(event) => setAmount(event.target.value)}
                    inputMode={currency === "VND" ? "numeric" : "decimal"}
                    type="number"
                    min={currency === "VND" ? "1" : "0.01"}
                    step={currency === "VND" ? "1" : "0.01"}
                    required
                    placeholder={currency === "VND" ? "1000000" : "100.00"}
                  />
                  <span className="hint">
                    {currency === "VND"
                      ? "Nhập số tiền bằng đồng Việt Nam."
                      : "Nhập số tiền USD, ví dụ 100.50."}
                  </span>
                  {amountPreview && (
                    <span className="mt-2 block text-sm font-semibold text-teal-700">
                      {amountPreview}
                    </span>
                  )}
                </label>
                <label>
                  <span className="label">Loại tiền</span>
                  <select value={currency} onChange={(e) => setCurrency(e.target.value)}>
                    <option value="VND">VND · Đồng Việt Nam</option>
                    <option value="USD">USD · Đô la Mỹ</option>
                  </select>
                </label>
                <label className="sm:col-span-2">
                  <span className="label">
                    Người thụ hưởng <span className="text-red-600">*</span>
                  </span>
                  <select
                    required
                    value={beneficiaryId}
                    onChange={(e) => setBeneficiaryId(e.target.value)}
                  >
                    <option value="" disabled>
                      Chọn người thụ hưởng
                    </option>
                    {beneficiaries.map((b) => (
                      <option value={b.id} key={b.id}>
                        {b.name} · {b.bank_code} · {b.account_masked}
                      </option>
                    ))}
                  </select>
                  {chosen && (
                    <p className="mt-2 rounded-xl bg-teal-50 px-4 py-3 text-sm text-teal-900">
                      <strong>{chosen.name}</strong>
                      <span className="block mt-1">
                        {chosen.bank_code} · {chosen.account_masked}
                      </span>
                    </p>
                  )}
                </label>
                <label>
                  <span className="label">
                    Hết hiệu lực lúc <span className="text-red-600">*</span>
                  </span>
                  <input
                    name="expires"
                    type="datetime-local"
                    min={localDateTime(new Date())}
                    defaultValue={defaultExpiry()}
                    required
                  />
                </label>
                <label>
                  <span className="label">Ghi chú (không bắt buộc)</span>
                  <input name="note" maxLength={1000} placeholder="Nội dung tham chiếu..." />
                </label>
              </div>
              <div className="flex flex-col-reverse gap-3 border-t border-slate-100 pt-5 sm:flex-row sm:justify-end">
                <Link href="/payment-requests" className="btn-secondary">
                  Hủy
                </Link>
                <LoadingButton busy={busy} busyLabel="Đang lưu...">
                  <Icon name="check" size={18} />
                  Lưu bản nháp
                </LoadingButton>
              </div>
            </form>
          )}
        </div>
        <aside className="surface-muted h-fit p-5">
          <div className="grid h-10 w-10 place-items-center rounded-xl bg-teal-100 text-teal-700">
            <Icon name="shield" size={21} />
          </div>
          <h2 className="mt-4 font-bold text-slate-900">Quy trình an toàn</h2>
          <ol className="mt-4 space-y-4 text-sm text-slate-600">
            <li>
              <strong className="text-slate-900">1. Tạo bản nháp</strong>
              <p className="mt-1">Kiểm tra thông tin thanh toán.</p>
            </li>
            <li>
              <strong className="text-slate-900">2. Phê duyệt & ký</strong>
              <p className="mt-1">Người có quyền xác nhận yêu cầu.</p>
            </li>
            <li>
              <strong className="text-slate-900">3. Chia sẻ tài liệu</strong>
              <p className="mt-1">Người nhận quét QR để kiểm chứng.</p>
            </li>
          </ol>
        </aside>
      </div>
    </Shell>
  );
}
