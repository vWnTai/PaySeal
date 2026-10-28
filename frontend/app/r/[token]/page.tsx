"use client";

import { FormEvent, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Icon } from "@/components/Icon";
import { api, formatMoney } from "@/lib/api";
import { useApiQuery } from "@/lib/useApiQuery";
import { Feedback } from "@/components/Feedback";
import { LoadingButton } from "@/components/LoadingButton";
import type { Verification } from "@/types";

type DocumentResult = { payment_signature: string; document_integrity: string; status: string };
const statusText: Record<string, { title: string; detail: string }> = {
  REVOKED: {
    title: "Yêu cầu đã bị thu hồi",
    detail: "Không thực hiện thanh toán theo yêu cầu này.",
  },
  DOCUMENT_MISMATCH: {
    title: "Tài liệu đã bị thay đổi",
    detail:
      "Nội dung PDF tải lên không khớp với bản đã ký. Không dùng thông tin trong tài liệu này.",
  },
  EXPIRED: { title: "Yêu cầu đã hết hiệu lực", detail: "Hãy yêu cầu người gửi phát hành bản mới." },
  SUPERSEDED: { title: "Đã có phiên bản mới hơn", detail: "Không thanh toán theo bản cũ này." },
  INVALID_SIGNATURE: {
    title: "Chữ ký không hợp lệ",
    detail: "Không tin cậy thông tin thanh toán này.",
  },
  CERTIFICATE_INVALID: {
    title: "Chứng thư không hợp lệ",
    detail: "Không tin cậy thông tin thanh toán này.",
  },
  KEY_COMPROMISED: {
    title: "Khóa ký không an toàn",
    detail: "Không tin cậy thông tin thanh toán này.",
  },
  KEY_REVOKED: {
    title: "Khóa ký đã bị thu hồi",
    detail: "Không tin cậy thông tin thanh toán này.",
  },
  UNKNOWN_ISSUER: {
    title: "Không xác định được bên phát hành",
    detail: "Không tin cậy thông tin thanh toán này.",
  },
};

export default function VerifyPage() {
  const { token } = useParams<{ token: string }>();
  const {
    data: result,
    error: queryError,
    loading,
    reload,
  } = useApiQuery<Verification>("/public/verify/" + token, false);
  const [doc, setDoc] = useState<DocumentResult | null>(null);
  const [error, setError] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [checking, setChecking] = useState(false);
  useEffect(() => {
    setDoc(null);
    setFile(null);
    setError("");
  }, [token]);
  function selectFile(next: File | undefined) {
    setDoc(null);
    setError("");
    setFile(null);
    if (!next) return;
    if (!next.name.toLowerCase().endsWith(".pdf")) {
      setError("Vui lòng chọn tệp PDF.");
      return;
    }
    setFile(next);
  }
  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file || checking) return;
    setError("");
    setChecking(true);
    setDoc(null);
    const body = new FormData();
    body.set("document", file);
    try {
      setDoc(
        await api<DocumentResult>(
          "/public/verify/" + token + "/document",
          { method: "POST", body },
          false,
        ),
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không thể kiểm tra tài liệu");
    } finally {
      setChecking(false);
    }
  }
  const effectiveStatus = doc?.status || result?.status;
  const verified = effectiveStatus === "VERIFIED";
  const warning = effectiveStatus ? statusText[effectiveStatus] : null;
  return (
    <main className="min-h-screen bg-[#f4f8f6] pb-12">
      <header className="bg-[#102b29] px-4 py-5 text-white">
        <div className="mx-auto flex max-w-3xl items-center justify-between">
          <div className="flex items-center gap-2.5">
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-teal-400 text-[#102b29]">
              <Icon name="shield" size={22} />
            </span>
            <span className="text-xl font-bold tracking-tight">PaySeal</span>
          </div>
          <span className="text-xs font-medium text-teal-100">Xác minh công khai</span>
        </div>
      </header>
      <div className="page-enter mx-auto max-w-3xl px-4 pt-7 sm:pt-10">
        <Feedback
          loading={loading}
          error={queryError}
          retry={() => {
            setDoc(null);
            void reload();
          }}
        />
        {error && (
          <div role="alert" className="alert-error mb-5">
            <Icon name="alert" size={22} />
            <div>
              <strong>Không thể xác minh</strong>
              <p className="mt-1">{error}</p>
            </div>
          </div>
        )}
        {result && (
          <>
            <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-[0_16px_45px_rgba(18,47,42,0.08)]">
              <div
                className={"p-6 text-white sm:p-8 " + (verified ? "bg-[#126f63]" : "bg-red-800")}
              >
                <div className="mb-4 grid h-12 w-12 place-items-center rounded-2xl bg-white/15">
                  <Icon name={verified ? "check" : "alert"} size={27} />
                </div>
                <p className="text-xs font-bold uppercase tracking-[0.16em]">
                  {verified ? "Trạng thái yêu cầu" : "Cảnh báo an toàn"}
                </p>
                <h1 className="mt-2 text-2xl font-bold tracking-tight sm:text-3xl">
                  {verified ? "Yêu cầu hợp lệ" : warning?.title || "Không thể xác minh"}
                </h1>
                <p className="mt-2 text-sm leading-relaxed text-white/90">
                  {verified
                    ? "Chữ ký của yêu cầu hợp lệ. Hãy kiểm tra mức xác minh doanh nghiệp, người nhận và số tiền bên dưới."
                    : warning?.detail ||
                      "Không thực hiện thanh toán trước khi xác nhận lại với bên phát hành."}
                </p>
              </div>
              {result.organization && result.payment && (
                <div className="p-5 sm:p-8">
                  <div className="rounded-xl bg-slate-50 p-4">
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                      Bên phát hành
                    </p>
                    <p className="mt-1 text-lg font-bold text-slate-900">
                      {result.organization.name}
                    </p>
                    <p className="mt-1 text-sm text-slate-500">
                      Mã số thuế: {result.organization.tax_id || "Chưa có"} · Mức xác thực:{" "}
                      {result.organization.verification_level}
                    </p>
                    {result.organization.verification_status && (
                      <p className="mt-3 rounded-lg border border-slate-200 bg-white p-3 text-sm text-slate-700">
                        {result.organization.verification_status === "APPROVED"
                          ? "Doanh nghiệp có hồ sơ đã được PaySeal xét duyệt thủ công và còn hiệu lực."
                          : result.organization.verification_status === "DEMO_SEEDED"
                            ? "Doanh nghiệp demo — chưa có hồ sơ được xét duyệt thực tế."
                            : "Doanh nghiệp chưa có hồ sơ xác minh còn hiệu lực. Chữ ký hợp lệ không thay thế việc kiểm tra doanh nghiệp."}
                      </p>
                    )}
                  </div>
                  <h2 className="section-title mt-7">Thông tin cần đối chiếu</h2>
                  <dl className="mt-4 grid gap-x-6 gap-y-5 sm:grid-cols-2">
                    <Info
                      label="Số tiền"
                      value={formatMoney(result.payment.amount_minor, result.payment.currency)}
                      emphasis
                    />
                    <Info label="Người thụ hưởng" value={result.payment.beneficiary} />
                    <Info
                      label="Ngân hàng / tài khoản"
                      value={result.payment.bank_code + " · " + result.payment.account_masked}
                    />
                    <Info label="Mã hóa đơn" value={result.payment.invoice_reference} />
                    <Info
                      label="Phát hành"
                      value={
                        result.issued_at ? new Date(result.issued_at).toLocaleString("vi-VN") : "—"
                      }
                    />
                    <Info
                      label="Hết hiệu lực"
                      value={
                        result.expires_at
                          ? new Date(result.expires_at).toLocaleString("vi-VN")
                          : "—"
                      }
                    />
                  </dl>
                  {result.warnings.map((w) => (
                    <p
                      key={w}
                      className="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"
                    >
                      <Icon name="alert" size={17} className="mr-2 inline-block align-middle" />
                      {w}
                    </p>
                  ))}
                </div>
              )}
            </section>
            <section className="card mt-5">
              <div className="flex items-start gap-3">
                <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-sky-50 text-sky-700">
                  <Icon name="upload" size={21} />
                </span>
                <div>
                  <h2 className="section-title">Kiểm tra file PDF</h2>
                  <p className="muted mt-1">
                    Quét QR chỉ kiểm tra trạng thái yêu cầu. Tải PDF lên để xác nhận file bạn nhận
                    được chưa bị sửa.
                  </p>
                </div>
              </div>
              <form onSubmit={upload} className="mt-5">
                <label
                  onDragOver={(event) => {
                    event.preventDefault();
                    if (!checking) setDragging(true);
                  }}
                  onDragLeave={() => setDragging(false)}
                  onDrop={(event) => {
                    event.preventDefault();
                    setDragging(false);
                    if (!checking) selectFile(event.dataTransfer.files[0]);
                  }}
                  className={
                    "block cursor-pointer rounded-xl border-2 border-dashed p-5 text-center transition-colors " +
                    (dragging
                      ? "border-teal-500 bg-teal-50"
                      : "border-slate-300 bg-slate-50 hover:border-teal-500")
                  }
                >
                  <Icon name="file" size={25} className="mx-auto text-teal-700" />
                  <span className="mt-2 block text-sm font-semibold text-slate-800">
                    {file?.name || "Kéo thả hoặc chọn file PDF"}
                  </span>
                  <span className="hint">
                    {file
                      ? (file.size / 1024 / 1024).toFixed(2) + " MB · Nhấn để đổi tệp"
                      : "Chỉ chấp nhận tệp PDF · Nhấn để chọn từ thiết bị"}
                  </span>
                  <input
                    name="document"
                    type="file"
                    accept="application/pdf,.pdf"
                    disabled={checking}
                    className="sr-only"
                    onChange={(e) => {
                      selectFile(e.target.files?.[0]);
                    }}
                  />
                </label>
                <LoadingButton
                  busy={checking}
                  busyLabel="Đang kiểm tra..."
                  disabled={!file}
                  className="btn-primary mt-4 w-full sm:w-auto"
                >
                  Xác minh PDF
                  <Icon name="arrowRight" size={17} />
                </LoadingButton>
              </form>
              {doc && (
                <div
                  role="status"
                  className={
                    "mt-5 rounded-xl border p-4 text-sm font-semibold " +
                    (doc.document_integrity === "MATCH"
                      ? "border-emerald-200 bg-emerald-50 text-emerald-900"
                      : "border-red-200 bg-red-50 text-red-900")
                  }
                >
                  {doc.document_integrity === "MATCH"
                    ? "PDF khớp với bản đã ký. Vẫn cần kiểm tra trạng thái yêu cầu phía trên."
                    : "PDF không khớp với bản đã ký. Không sử dụng tài liệu này."}
                </div>
              )}
            </section>
          </>
        )}
        <p className="mx-auto mt-7 max-w-xl text-center text-xs leading-relaxed text-slate-500">
          PaySeal xác minh thông tin thanh toán; không thực hiện chuyển tiền. Nếu có nghi ngờ, hãy
          liên hệ trực tiếp bên phát hành qua kênh độc lập.
        </p>
      </div>
    </main>
  );
}

function Info({
  label,
  value,
  emphasis = false,
}: {
  label: string;
  value: string;
  emphasis?: boolean;
}) {
  return (
    <div>
      <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</dt>
      <dd
        className={
          "mt-1 break-words font-semibold text-slate-900 " + (emphasis ? "text-2xl" : "text-base")
        }
      >
        {value}
      </dd>
    </div>
  );
}
