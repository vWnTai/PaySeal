"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { Shell } from "@/components/Shell";
import { Feedback } from "@/components/Feedback";
import { LoadingButton } from "@/components/LoadingButton";
import { Icon } from "@/components/Icon";
import { useSession } from "@/components/SessionProvider";
import { api, apiRequest } from "@/lib/api";
import { useApiQuery } from "@/lib/useApiQuery";
import { verificationLabels } from "@/lib/operations";
import type { BusinessVerification } from "@/types";

export default function ReviewPage() {
  const { user } = useSession();
  const [offset, setOffset] = useState(0);
  const [filter, setFilter] = useState("PENDING");
  const enabled = Boolean(user?.is_platform_reviewer && user.mfa_enabled);
  const queue = useApiQuery<BusinessVerification[]>(
    enabled ? "/platform/verifications?offset=" + offset + "&status=" + filter : null,
  );
  const [selected, setSelected] = useState<string | null>(null);
  const [decision, setDecision] = useState("CHANGES_REQUESTED");
  const [busy, setBusy] = useState(false);
  const [downloading, setDownloading] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function download(item: BusinessVerification) {
    setDownloading(item.id);
    setError("");
    try {
      const response = await apiRequest("/platform/verifications/" + item.id + "/document");
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = "business-" + item.id + ".pdf";
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không thể tải hồ sơ.");
    } finally {
      setDownloading("");
    }
  }

  async function review(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !selected) return;
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const revoke = queue.data?.find((item) => item.id === selected)?.status === "APPROVED";
      await api("/platform/verifications/" + selected + (revoke ? "/revoke" : "/review"), {
        method: "POST",
        body: JSON.stringify({
          reason: form.get("reason"),
          totp_code: form.get("totp_code") || null,
          ...(!revoke
            ? {
                decision,
                registration_checked: form.has("registration_checked"),
                tax_checked: form.has("tax_checked"),
                authority_checked: form.has("authority_checked"),
              }
            : {}),
        }),
      });
      setSelected(null);
      await queue.reload();
      setNotice(
        "Đã lưu kết quả xét duyệt và nhật ký. Doanh nghiệp có thể xem phản hồi trong hồ sơ.",
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không thể lưu kết quả.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Shell
      title="Xét duyệt doanh nghiệp"
      description="Khu vực người xét duyệt độc lập. Không tự duyệt tổ chức mà bạn là thành viên."
    >
      <div className="surface-muted mb-5 flex items-start gap-3 p-4 text-sm leading-relaxed text-slate-600">
        <Icon name="shield" className="shrink-0 text-teal-700" />
        <p>
          Chỉ chấp thuận sau khi đối chiếu với nguồn độc lập và ghi rõ căn cứ, không chỉ vì đã có
          một tệp PDF. Hồ sơ chưa được quét mã độc tự động — chỉ mở trong môi trường kiểm tra an
          toàn.
        </p>
      </div>
      {user && !enabled && (
        <section className="card">
          <p className="muted">
            Bạn cần quyền xét duyệt do quản trị hệ thống cấp và phải bật MFA. Chủ tổ chức không tự
            cấp được quyền này.
          </p>
          <Link href="/settings/security" className="btn-primary mt-4">
            Thiết lập bảo mật
          </Link>
        </section>
      )}
      <Feedback loading={queue.loading} error={queue.error} retry={queue.reload} />
      {enabled && (
        <label className="mb-5 block max-w-sm">
          <span id="review-filter-label" className="label">
            Lọc trạng thái hồ sơ
          </span>
          <select
            aria-labelledby="review-filter-label"
            value={filter}
            onChange={(event) => {
              setFilter(event.target.value);
              setOffset(0);
              setSelected(null);
            }}
          >
            {["PENDING", "APPROVED", "CHANGES_REQUESTED", "REJECTED", "REVOKED", "STALE"].map(
              (status) => (
                <option key={status} value={status}>
                  {verificationLabels[status]}
                </option>
              ),
            )}
          </select>
        </label>
      )}
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
      {enabled && !queue.loading && queue.data?.length === 0 && (
        <section className="card py-12 text-center">
          <Icon name="check" size={32} className="mx-auto text-teal-700" />
          <h2 className="section-title mt-3">Không có hồ sơ phù hợp ở trang này</h2>
          <p className="muted mt-2">
            Hồ sơ của tổ chức bạn tham gia không xuất hiện trong hàng đợi.
          </p>
        </section>
      )}
      <div className="space-y-5">
        {queue.data?.map((item) => (
          <section key={item.id} className="card">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="eyebrow">
                  {verificationLabels[item.status]} ·{" "}
                  {new Date(item.created_at).toLocaleDateString("vi-VN")}
                </p>
                <h2 className="section-title mt-2">{item.profile.name}</h2>
                <p className="muted mt-2">
                  MST {item.profile.tax_id} · {item.profile.domain}
                </p>
              </div>
              <LoadingButton
                type="button"
                busy={downloading === item.id}
                busyLabel="Đang tải..."
                className="btn-secondary"
                onClick={() => download(item)}
              >
                <Icon name="download" size={17} />
                Tải hồ sơ PDF
              </LoadingButton>
            </div>
            <dl className="mt-5 grid gap-4 text-sm sm:grid-cols-2">
              {[
                ["Người đại diện", item.representative_name],
                ["Đăng ký doanh nghiệp", item.registration_number],
                ["Địa chỉ", item.registered_address],
                ["Liên hệ", item.contact_email],
              ].map(([label, value]) => (
                <div key={label}>
                  <dt className="text-slate-500">{label}</dt>
                  <dd className="mt-1 break-words font-medium text-slate-800">{value}</dd>
                </div>
              ))}
            </dl>
            <p className="hint mt-4 break-all">SHA-256 hồ sơ: {item.document_sha256}</p>
            {item.review_reason && (
              <p className="surface-muted mt-3 whitespace-pre-wrap p-3 text-sm">
                {item.review_reason}
              </p>
            )}
            {selected !== item.id ? (
              ["PENDING", "APPROVED"].includes(item.status) && (
                <button
                  type="button"
                  className="btn-primary mt-5"
                  disabled={busy}
                  onClick={() => {
                    setSelected(item.id);
                    setDecision("CHANGES_REQUESTED");
                    setError("");
                  }}
                >
                  {item.status === "APPROVED" ? "Thu hồi xác minh" : "Xét duyệt hồ sơ"}
                  <Icon name="arrowRight" size={17} />
                </button>
              )
            ) : (
              <form onSubmit={review} className="surface-muted page-enter mt-5 p-4 sm:p-5">
                <fieldset disabled={busy} className="space-y-4">
                  {item.status === "PENDING" ? (
                    <>
                      <label>
                        <span id="review-decision-label" className="label">
                          Kết quả xét duyệt
                        </span>
                        <select
                          aria-labelledby="review-decision-label"
                          value={decision}
                          onChange={(event) => setDecision(event.target.value)}
                        >
                          <option value="CHANGES_REQUESTED">Yêu cầu bổ sung</option>
                          <option value="REJECTED">Từ chối hồ sơ</option>
                          <option value="APPROVED">Chấp thuận hồ sơ</option>
                        </select>
                      </label>
                      <div className="space-y-3">
                        {[
                          ["registration_checked", "Đã đối chiếu giấy đăng ký với nguồn độc lập"],
                          ["tax_checked", "Đã đối chiếu mã số thuế và tên pháp lý"],
                          ["authority_checked", "Đã kiểm tra quyền đại diện / giấy ủy quyền"],
                        ].map(([name, label]) => (
                          <label
                            key={name}
                            className="flex! items-start gap-3 text-sm text-slate-700"
                          >
                            <input
                              type="checkbox"
                              name={name}
                              required={decision === "APPROVED"}
                              className="mt-0.5 h-4 w-4 shrink-0 accent-teal-700"
                            />
                            <span>{label}</span>
                          </label>
                        ))}
                      </div>
                    </>
                  ) : (
                    <p className="text-sm text-red-800">
                      Thu hồi sẽ đưa doanh nghiệp về trạng thái chưa xác minh và chặn tạo lệnh
                      chuyển mới. Giao dịch đã có kết quả không bị đảo ngược.
                    </p>
                  )}
                  <label>
                    <span className="label">Căn cứ kiểm tra / yêu cầu bổ sung</span>
                    <textarea
                      name="reason"
                      required
                      minLength={20}
                      maxLength={1000}
                      rows={4}
                      placeholder="Ghi nguồn đối chiếu, ngày kiểm tra và nội dung cần bổ sung. Phản hồi này hiển thị cho doanh nghiệp."
                    />
                  </label>
                  <label>
                    <span className="label">Mã xác thực 6 số</span>
                    <input
                      name="totp_code"
                      required
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      pattern="[0-9]{6}"
                      maxLength={6}
                      placeholder="000000"
                    />
                  </label>
                  <div className="flex flex-wrap gap-3">
                    <LoadingButton busy={busy} busyLabel="Đang lưu...">
                      {item.status === "APPROVED"
                        ? "Xác nhận thu hồi xác minh"
                        : "Lưu kết quả xét duyệt"}
                    </LoadingButton>
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={() => setSelected(null)}
                    >
                      Hủy
                    </button>
                  </div>
                </fieldset>
              </form>
            )}
          </section>
        ))}
      </div>
      {enabled && (
        <div className="mt-5 flex items-center justify-between">
          <button
            type="button"
            className="btn-secondary"
            disabled={offset === 0 || queue.loading}
            onClick={() => setOffset(Math.max(0, offset - 50))}
          >
            Trang trước
          </button>
          <span className="muted">Trang {offset / 50 + 1}</span>
          <button
            type="button"
            className="btn-secondary"
            disabled={queue.loading || (queue.data?.length || 0) < 50}
            onClick={() => setOffset(offset + 50)}
          >
            Trang tiếp
          </button>
        </div>
      )}
    </Shell>
  );
}
