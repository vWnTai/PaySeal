"use client";

import Link from "next/link";
import { useState } from "react";
import { Shell } from "@/components/Shell";
import { Feedback } from "@/components/Feedback";
import { Icon } from "@/components/Icon";
import { useApiQuery } from "@/lib/useApiQuery";
import { normalizeSearch } from "@/lib/payment";
import type { Beneficiary } from "@/types";

export default function Beneficiaries() {
  const { data, error, loading, reload } = useApiQuery<Beneficiary[]>("/beneficiaries");
  const [query, setQuery] = useState("");
  const items = (data || []).filter((item) =>
    normalizeSearch(item.name + " " + item.bank_code + " " + item.account_masked).includes(
      normalizeSearch(query),
    ),
  );
  return (
    <Shell
      title="Người thụ hưởng"
      description="Quản lý tài khoản nhận tiền đã đăng ký trong tổ chức."
      action={
        <Link href="/beneficiaries/new" className="btn-primary w-full sm:w-auto">
          <Icon name="plus" size={18} />
          Thêm người thụ hưởng
        </Link>
      }
    >
      {data && data.length > 0 && (
        <label className="relative mb-5 block max-w-lg">
          <span className="sr-only">Tìm người thụ hưởng</span>
          <Icon
            name="search"
            size={18}
            className="pointer-events-none absolute left-3.5 top-3.5 text-slate-400"
          />
          <input
            type="search"
            className="!pl-10"
            placeholder="Tìm tên, ngân hàng, tài khoản..."
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
      )}
      <Feedback
        loading={loading}
        error={error}
        retry={reload}
        empty={!loading && !error && !items.length}
        emptyTitle={query ? "Không tìm thấy người thụ hưởng" : "Chưa có người thụ hưởng"}
        emptyMessage={
          query
            ? "Thử từ khóa khác hoặc xóa tìm kiếm."
            : "Thêm tài khoản nhận tiền để tạo yêu cầu thanh toán."
        }
        action={
          query ? (
            <button type="button" className="btn-secondary" onClick={() => setQuery("")}>
              Xóa tìm kiếm
            </button>
          ) : (
            <Link href="/beneficiaries/new" className="btn-primary">
              Thêm người thụ hưởng
            </Link>
          )
        }
      />
      <div className="stagger grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {items.map((b) => (
          <article className="card" key={b.id}>
            <div className="flex items-start justify-between gap-3">
              <span className="grid h-11 w-11 place-items-center rounded-xl bg-teal-50 text-teal-700">
                <Icon name="wallet" size={21} />
              </span>
              <span className="badge border-teal-200 bg-teal-50 text-teal-800">
                {b.status === "ACTIVE" ? "Đang dùng" : b.status}
              </span>
            </div>
            <h2 className="mt-5 text-lg font-bold text-slate-900">{b.name}</h2>
            <p className="muted mt-1">{b.bank_code}</p>
            <div className="mt-5 rounded-xl bg-slate-50 px-4 py-3 font-mono text-sm text-slate-700">
              {b.account_masked}
            </div>
          </article>
        ))}
      </div>
    </Shell>
  );
}
