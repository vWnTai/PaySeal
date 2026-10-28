"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { Shell } from "@/components/Shell";
import { Feedback } from "@/components/Feedback";
import { Icon } from "@/components/Icon";
import { api, session } from "@/lib/api";
import { useApiQuery } from "@/lib/useApiQuery";
import { LoadingButton } from "@/components/LoadingButton";
import { useSession } from "@/components/SessionProvider";
import type { Organization } from "@/types";
import { verificationLabels, operationTone } from "@/lib/operations";

export default function OrganizationPage() {
  const [organizationId, setOrganizationId] = useState("");
  const {
    data: item,
    error: queryError,
    loading,
    reload,
  } = useApiQuery<Organization>(organizationId ? "/organizations/" + organizationId : null);
  const { reloadUser } = useSession();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    setOrganizationId(session().organizationId);
  }, []);
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(event.currentTarget);
    try {
      const result = await api<Organization>("/organizations", {
        method: "POST",
        body: JSON.stringify({
          name: data.get("name"),
          tax_id: data.get("tax"),
          domain: data.get("domain"),
        }),
      });
      localStorage.setItem("payseal_org", result.id);
      setOrganizationId(result.id);
      await reloadUser();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không thể tạo tổ chức");
      setBusy(false);
    }
  }
  return (
    <Shell title="Tổ chức" description="Thông tin đơn vị phát hành và không gian làm việc của bạn.">
      <Feedback loading={loading} error={queryError} retry={reload} />
      {!loading &&
        !queryError &&
        (item ? (
          <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_280px]">
            <section className="card">
              <div className="flex items-start gap-4">
                <span className="grid h-12 w-12 shrink-0 place-items-center rounded-xl bg-teal-50 text-teal-700">
                  <Icon name="building" size={25} />
                </span>
                <div>
                  <p className="eyebrow">Tổ chức phát hành</p>
                  <h2 className="mt-1 text-2xl font-bold text-slate-900">{item.name}</h2>
                </div>
              </div>
              <p
                className={
                  "mt-5 rounded-xl border p-3 text-sm font-medium " +
                  operationTone(item.verification_status || "UNVERIFIED")
                }
              >
                {verificationLabels[item.verification_status || "UNVERIFIED"]}
              </p>
              {item.verification_valid_until && (
                <p className="hint">
                  Hiệu lực xét duyệt đến{" "}
                  {new Date(item.verification_valid_until).toLocaleDateString("vi-VN")}
                </p>
              )}
              <dl className="mt-7 grid gap-5 sm:grid-cols-2">
                <Info label="Mã số thuế" value={item.tax_id} />
                <Info label="Tên miền" value={item.domain} />
                <Info label="Trạng thái" value={item.status} />
                <Info label="Mã tổ chức" value={item.id} />
              </dl>
            </section>
            <aside className="card h-fit">
              <h2 className="section-title">Quản lý tổ chức</h2>
              <p className="muted mt-2">Thêm người dùng và phân quyền xử lý yêu cầu.</p>
              <Link href="/organization/members" className="btn-secondary mt-5 w-full">
                Quản lý thành viên <Icon name="arrowRight" size={17} />
              </Link>
              <Link href="/organization/verification" className="btn-primary mt-3 w-full">
                Hồ sơ xác minh <Icon name="shield" size={17} />
              </Link>
            </aside>
          </div>
        ) : (
          <form onSubmit={create} className="card max-w-2xl space-y-5">
            {error && (
              <div className="alert-error" role="alert">
                <Icon name="alert" size={20} />
                <span>{error}</span>
              </div>
            )}
            <div>
              <h2 className="section-title">Tạo không gian làm việc</h2>
              <p className="muted mt-1">Tổ chức mới bắt đầu ở trạng thái chưa được xác minh.</p>
            </div>
            <label>
              <span className="label">Tên pháp lý</span>
              <input
                name="name"
                required
                minLength={2}
                maxLength={200}
                placeholder="Tên doanh nghiệp hoặc tổ chức"
              />
            </label>
            <label>
              <span className="label">Mã số thuế</span>
              <input
                name="tax"
                required
                minLength={3}
                maxLength={64}
                pattern="[A-Za-z0-9._-]+"
                placeholder="Nhập mã số thuế"
              />
            </label>
            <label>
              <span className="label">Tên miền</span>
              <input name="domain" required minLength={3} maxLength={253} placeholder="congty.vn" />
            </label>
            <LoadingButton
              busy={busy}
              busyLabel="Đang tạo..."
              className="btn-primary w-full sm:w-auto"
            >
              Tạo tổ chức
            </LoadingButton>
          </form>
        ))}
    </Shell>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className="mt-1 break-all font-semibold text-slate-900">{value}</dd>
    </div>
  );
}
