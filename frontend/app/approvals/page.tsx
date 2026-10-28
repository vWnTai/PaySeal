"use client";

import Link from "next/link";
import { Shell } from "@/components/Shell";
import { Feedback } from "@/components/Feedback";
import { Icon } from "@/components/Icon";
import { formatMoney } from "@/lib/api";
import { useApiQuery } from "@/lib/useApiQuery";
import type { Payment } from "@/types";

export default function Approvals() {
  const { data, error, loading, reload } = useApiQuery<Payment[]>("/payment-requests");
  const items = (data || []).filter((item) => item.status === "PENDING_APPROVAL");
  return (
    <Shell
      title="Cần phê duyệt"
      description="Xem kỹ thông tin người nhận và số tiền trước khi xác nhận."
    >
      <Feedback
        loading={loading}
        error={error}
        retry={reload}
        empty={!loading && !error && !items.length}
        emptyTitle="Không có yêu cầu chờ duyệt"
        emptyMessage="Khi có yêu cầu mới, chúng sẽ xuất hiện ở đây."
      />
      <div className="stagger grid gap-3">
        {items.map((p) => (
          <Link
            className="interactive-card flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between"
            href={"/payment-requests/" + p.id}
            key={p.id}
          >
            <div className="min-w-0">
              <p className="font-bold text-slate-900">{p.invoice_reference}</p>
              <p className="muted mt-1">
                {p.beneficiary_name} · {p.bank_code} · {p.account_masked}
              </p>
              <p className="mt-2 text-xs font-medium text-slate-500">
                Đã duyệt {p.approvals_completed}/{p.approvals_required}
              </p>
            </div>
            <div className="flex items-center justify-between gap-4 sm:justify-end">
              <span className="text-lg font-bold text-slate-900">
                {formatMoney(p.amount_minor, p.currency)}
              </span>
              <span className="grid h-9 w-9 place-items-center rounded-full bg-teal-50 text-teal-700">
                <Icon name="arrowRight" size={17} />
              </span>
            </div>
          </Link>
        ))}
      </div>
    </Shell>
  );
}
