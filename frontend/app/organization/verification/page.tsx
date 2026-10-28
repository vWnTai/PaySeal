"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { Shell } from "@/components/Shell";
import { Feedback } from "@/components/Feedback";
import { Icon } from "@/components/Icon";
import { LoadingButton } from "@/components/LoadingButton";
import { useSession } from "@/components/SessionProvider";
import { api, session } from "@/lib/api";
import { useApiQuery } from "@/lib/useApiQuery";
import { operationTone, verificationLabels } from "@/lib/operations";
import type { BusinessVerification, Organization } from "@/types";

export default function VerificationPage() {
  const { user, reloadUser } = useSession();
  const [organizationId, setOrganizationId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  useEffect(() => setOrganizationId(session().organizationId), []);
  const role = user?.organizations.find((item) => item.id === organizationId)?.role;
  const allowed = role === "OWNER" || role === "AUDITOR";
  const path = "/organizations/" + organizationId;
  const history = useApiQuery<BusinessVerification[]>(allowed ? path + "/verification" : null);
  const organization = useApiQuery<Organization>(organizationId ? path : null);
  const status = organization.data?.verification_status || "UNVERIFIED";
  const canSubmit = role === "OWNER" && !["PENDING", "APPROVED"].includes(status);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const form = event.currentTarget;
    const body = new FormData(form);
    const file = body.get("document");
    if (!(file instanceof File) || file.size > 5 * 1024 * 1024 || !file.size) {
      setError("Chọn hồ sơ PDF không rỗng, tối đa 5 MB.");
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await api(path + "/verification", { method: "POST", body });
      form.reset();
      await Promise.all([history.reload(), organization.reload(), reloadUser()]);
      setNotice("Đã gửi hồ sơ. Người xét duyệt độc lập sẽ kiểm tra và phản hồi tại đây.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không thể gửi hồ sơ.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Shell
      title="Xác minh doanh nghiệp"
      description="Nộp hồ sơ và theo dõi từng bước xét duyệt độc lập."
      action={
        <Link href="/organization" className="btn-secondary">
          <Icon name="arrowLeft" size={17} />
          Tổ chức
        </Link>
      }
    >
      <section className="card mb-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="eyebrow">Hồ sơ doanh nghiệp</p>
            <h2 className="section-title mt-2">{organization.data?.name || "Tổ chức của bạn"}</h2>
            <p className="muted mt-2">
              Xét duyệt thủ công bởi PaySeal, không phải chứng nhận từ cơ quan nhà nước.
            </p>
          </div>
          <span className={"badge " + operationTone(status)}>
            {verificationLabels[status] || status}
          </span>
        </div>
        <ol className="mt-6 grid gap-3 sm:grid-cols-3" aria-label="Quy trình xác minh">
          {["Chuẩn bị hồ sơ PDF", "Gửi và chờ xét duyệt", "Nhận kết quả / bổ sung"].map(
            (label, index) => (
              <li key={label} className="surface-muted flex items-center gap-3 p-3 text-sm">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-teal-100 font-bold text-teal-800">
                  {index + 1}
                </span>
                {label}
              </li>
            ),
          )}
        </ol>
      </section>
      <Feedback
        loading={history.loading || organization.loading}
        error={history.error || organization.error}
        retry={() => {
          void history.reload();
          void organization.reload();
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
      {user && !allowed && (
        <section className="card">
          <p className="muted">
            Chủ tổ chức gửi hồ sơ; chủ tổ chức và kiểm toán viên có thể xem kết quả. Hãy liên hệ
            người quản lý của bạn.
          </p>
        </section>
      )}
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_350px]">
        <div className="space-y-5">
          {history.data?.map((item) => (
            <section key={item.id} className="card page-enter">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="section-title">
                  Hồ sơ {new Date(item.created_at).toLocaleDateString("vi-VN")}
                </h2>
                <span className={"badge " + operationTone(item.status)}>
                  {verificationLabels[item.status]}
                </span>
              </div>
              <p className="muted mt-3">
                Người đại diện: {item.representative_name} · Đăng ký: {item.registration_number}
              </p>
              {item.review_reason && (
                <div className="surface-muted mt-4 p-4">
                  <h3 className="text-sm font-semibold">Phản hồi xét duyệt</h3>
                  <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-slate-700">
                    {item.review_reason}
                  </p>
                </div>
              )}
              {item.valid_until && (
                <p className="hint">
                  Hiệu lực đến {new Date(item.valid_until).toLocaleDateString("vi-VN")}. Thay đổi
                  thông tin doanh nghiệp cần xác minh lại.
                </p>
              )}
            </section>
          ))}
          {canSubmit && (
            <form onSubmit={submit} className="card">
              <h2 className="section-title">
                {history.data?.length ? "Gửi hồ sơ mới" : "Bắt đầu xác minh"}
              </h2>
              <p className="muted mt-2">
                Gộp giấy đăng ký doanh nghiệp và tài liệu chứng minh quyền đại diện vào một PDF.
                Không gửi mật khẩu, OTP hoặc thông tin đăng nhập ngân hàng.
              </p>
              <fieldset disabled={busy} className="mt-5 space-y-5">
                <div className="grid gap-5 sm:grid-cols-2">
                  <label>
                    <span className="label">Số đăng ký doanh nghiệp</span>
                    <input
                      name="registration_number"
                      required
                      minLength={3}
                      maxLength={100}
                      placeholder="Theo giấy đăng ký"
                    />
                  </label>
                  <label>
                    <span className="label">Họ tên người đại diện</span>
                    <input
                      name="representative_name"
                      required
                      minLength={2}
                      maxLength={160}
                      autoComplete="name"
                    />
                  </label>
                </div>
                <label>
                  <span className="label">Địa chỉ đăng ký</span>
                  <input
                    name="registered_address"
                    required
                    minLength={5}
                    maxLength={500}
                    autoComplete="street-address"
                  />
                </label>
                <label>
                  <span className="label">Email liên hệ doanh nghiệp</span>
                  <input
                    name="contact_email"
                    type="email"
                    required
                    maxLength={320}
                    autoComplete="email"
                  />
                </label>
                <label className="rounded-2xl border-2 border-dashed border-teal-200 bg-teal-50/40 p-5 transition hover:border-teal-500">
                  <span className="label flex items-center gap-2">
                    <Icon name="upload" />
                    Hồ sơ PDF · tối đa 5 MB
                  </span>
                  <input name="document" type="file" required accept="application/pdf,.pdf" />
                </label>
                <label className="flex! items-start gap-3 text-sm leading-relaxed text-slate-600">
                  <input
                    type="checkbox"
                    name="attested"
                    value="true"
                    required
                    className="mt-1 h-4 w-4 shrink-0 accent-teal-700"
                  />
                  <span>
                    Tôi được phép đại diện doanh nghiệp, xác nhận hồ sơ đúng sự thật và đồng ý để
                    PaySeal xử lý hồ sơ cho mục đích xác minh.
                  </span>
                </label>
                <LoadingButton
                  busy={busy}
                  busyLabel="Đang gửi hồ sơ..."
                  className="btn-primary w-full sm:w-auto"
                >
                  Gửi hồ sơ xét duyệt
                  <Icon name="arrowRight" size={17} />
                </LoadingButton>
              </fieldset>
            </form>
          )}
        </div>
        <aside className="card h-fit">
          <Icon name="shield" size={28} className="text-teal-700" />
          <h2 className="section-title mt-3">Hồ sơ được bảo vệ</h2>
          <p className="muted mt-3">
            PDF lưu trong kho riêng, không có liên kết công khai. Chỉ người xét duyệt có quyền mới
            tải được hồ sơ; các lượt tải được ghi nhật ký.
          </p>
          <p className="muted mt-3">
            Người thuộc doanh nghiệp không được tự xét duyệt. Kết quả chấp thuận có hiệu lực 12
            tháng; cần kiểm tra độc lập giấy đăng ký, mã số thuế và quyền đại diện.
          </p>
          {status === "PENDING" && (
            <p className="mt-4 rounded-xl bg-amber-50 p-3 text-sm text-amber-900">
              Hồ sơ đang chờ xử lý. Bạn không cần gửi lại hoặc tự bật trạng thái xác minh.
            </p>
          )}
        </aside>
      </div>
    </Shell>
  );
}
