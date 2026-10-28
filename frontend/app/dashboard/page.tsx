"use client";

import Link from "next/link";
import { Shell } from "@/components/Shell";
import { Feedback } from "@/components/Feedback";
import { StatusBadge } from "@/components/StatusBadge";
import { Icon } from "@/components/Icon";
import { formatMoney } from "@/lib/api";
import { useApiQuery } from "@/lib/useApiQuery";
import type { Payment } from "@/types";

export default function Dashboard() {
  const { data, error, loading, reload } = useApiQuery<Payment[]>("/payment-requests");
  const items = data || [];
  const now = new Date();
  const monthCount = items.filter((p) => {
    const created = new Date(p.created_at);
    return created.getMonth() === now.getMonth() && created.getFullYear() === now.getFullYear();
  }).length;
  const pending = items.filter((p) => p.status === "PENDING_APPROVAL");
  const approved = items.filter((p) => p.status === "APPROVED");
  const stats = [
    {
      label: "Tạo trong tháng",
      value: monthCount,
      icon: "file" as const,
      tone: "bg-sky-50 text-sky-700",
      href: "/payment-requests",
    },
    {
      label: "Chờ phê duyệt",
      value: pending.length,
      icon: "clock" as const,
      tone: "bg-amber-50 text-amber-700",
      href: "/approvals",
    },
    {
      label: "Sẵn sàng ký",
      value: approved.length,
      icon: "check" as const,
      tone: "bg-teal-50 text-teal-700",
      href: "/payment-requests?status=APPROVED",
    },
    {
      label: "Đã ký",
      value: items.filter((p) => p.status === "SIGNED").length,
      icon: "shield" as const,
      tone: "bg-emerald-50 text-emerald-700",
      href: "/payment-requests?status=SIGNED",
    },
  ];
  return (
    <Shell
      title="Tổng quan"
      description="Theo dõi yêu cầu thanh toán và xử lý những việc cần làm."
      action={
        <Link className="btn-primary w-full sm:w-auto" href="/payment-requests/new">
          <Icon name="plus" size={18} />
          Tạo yêu cầu
        </Link>
      }
    >
      <Feedback loading={loading} error={error} retry={reload} />
      {!loading && !error && (
        <>
          <section
            className="stagger grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4"
            aria-label="Thống kê"
          >
            {stats.map((stat) => (
              <Link href={stat.href} className="stat-card !p-4 sm:!p-6" key={stat.label}>
                <div>
                  <p className="text-sm font-medium text-slate-500">{stat.label}</p>
                  <p className="mt-3 text-3xl font-bold tracking-tight text-slate-900">
                    {stat.value}
                  </p>
                </div>
                <span
                  className={
                    "hidden h-11 w-11 shrink-0 place-items-center rounded-xl sm:grid " + stat.tone
                  }
                >
                  <Icon name={stat.icon} size={21} />
                </span>
              </Link>
            ))}
          </section>
          {(pending.length > 0 || approved.length > 0) && (
            <section className="mt-6 rounded-2xl border border-teal-200 bg-teal-50 p-5 sm:flex sm:items-center sm:justify-between sm:gap-5">
              <div>
                <p className="eyebrow">Cần xử lý</p>
                <h2 className="mt-1 text-lg font-bold text-slate-900">
                  {pending.length} yêu cầu chờ duyệt · {approved.length} yêu cầu chờ ký
                </h2>
                <p className="muted mt-1">Mở từng yêu cầu để xem thông tin trước khi quyết định.</p>
              </div>
              <Link
                href={pending.length ? "/approvals" : "/payment-requests?status=APPROVED"}
                className="btn-secondary mt-4 w-full sm:mt-0 sm:w-auto"
              >
                Xem yêu cầu <Icon name="arrowRight" size={18} />
              </Link>
            </section>
          )}
          <section className="card mt-6">
            <div className="mb-5 flex items-center justify-between gap-3">
              <div>
                <h2 className="section-title">Yêu cầu gần đây</h2>
                <p className="muted mt-1">Các giao dịch mới nhất trong tổ chức.</p>
              </div>
              <Link href="/payment-requests" className="btn-quiet shrink-0">
                Xem tất cả <Icon name="arrowRight" size={17} />
              </Link>
            </div>
            {items.length === 0 ? (
              <div className="rounded-xl bg-slate-50 px-5 py-10 text-center">
                <p className="font-semibold">Chưa có yêu cầu thanh toán</p>
                <p className="muted mt-1">Tạo yêu cầu đầu tiên để bắt đầu quy trình xác nhận.</p>
                <Link href="/payment-requests/new" className="btn-primary mt-5">
                  Tạo yêu cầu
                </Link>
              </div>
            ) : (
              <div className="divide-y divide-slate-100">
                {items.slice(0, 6).map((p) => (
                  <Link
                    href={"/payment-requests/" + p.id}
                    key={p.id}
                    className="flex flex-col gap-3 py-4 first:pt-0 last:pb-0 hover:bg-slate-50/60 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div className="min-w-0">
                      <p className="truncate font-semibold text-slate-900">{p.invoice_reference}</p>
                      <p className="muted mt-1 truncate">
                        {p.beneficiary_name} · {new Date(p.created_at).toLocaleDateString("vi-VN")}
                      </p>
                    </div>
                    <div className="flex items-center justify-between gap-4 sm:justify-end">
                      <span className="font-bold text-slate-900">
                        {formatMoney(p.amount_minor, p.currency)}
                      </span>
                      <StatusBadge status={p.status} />
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </Shell>
  );
}
