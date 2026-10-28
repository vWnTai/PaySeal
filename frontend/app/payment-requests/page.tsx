"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Shell } from "@/components/Shell";
import { Feedback } from "@/components/Feedback";
import { StatusBadge } from "@/components/StatusBadge";
import { Icon } from "@/components/Icon";
import { formatMoney } from "@/lib/api";
import { useApiQuery } from "@/lib/useApiQuery";
import { normalizeSearch, paymentStatuses } from "@/lib/payment";
import type { Payment } from "@/types";

const filters = [
  { value: "all", label: "Tất cả trạng thái" },
  ...paymentStatuses.filter((item) => item.value !== "VERIFIED"),
];
const PAGE_SIZE = 12;

export default function Payments() {
  const { data, error, loading, reload } = useApiQuery<Payment[]>("/payment-requests");
  const items = useMemo(() => data || [], [data]);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [sort, setSort] = useState("recent");
  const [page, setPage] = useState(1);
  useEffect(() => {
    const status = new URLSearchParams(window.location.search).get("status");
    if (status && filters.some((item) => item.value === status)) setFilter(status);
  }, []);
  const visible = useMemo(
    () =>
      items
        .filter(
          (p) =>
            (filter === "all" || p.status === filter) &&
            normalizeSearch(
              p.invoice_reference +
                " " +
                p.beneficiary_name +
                " " +
                p.bank_code +
                " " +
                p.account_masked,
            ).includes(normalizeSearch(query)),
        )
        .sort((a, b) =>
          sort === "expiry"
            ? Date.parse(a.expires_at) - Date.parse(b.expires_at)
            : Date.parse(b.created_at) - Date.parse(a.created_at),
        ),
    [items, filter, query, sort],
  );
  const pageCount = Math.max(1, Math.ceil(visible.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount);
  const paged = visible.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);
  function resetFilters() {
    setQuery("");
    setFilter("all");
    setPage(1);
  }
  return (
    <Shell
      title="Yêu cầu thanh toán"
      description="Tìm kiếm, theo dõi trạng thái và mở chi tiết từng yêu cầu."
      action={
        <Link className="btn-primary w-full sm:w-auto" href="/payment-requests/new">
          <Icon name="plus" size={18} />
          Tạo yêu cầu
        </Link>
      }
    >
      <Feedback loading={loading} error={error} retry={reload} />
      {!loading && !error && (
        <div className="card">
          <div className="mb-5 flex flex-col gap-3 sm:flex-row">
            <label className="relative block flex-1">
              <span className="sr-only">Tìm theo hóa đơn hoặc người thụ hưởng</span>
              <Icon
                name="search"
                size={18}
                className="pointer-events-none absolute left-3.5 top-3.5 text-slate-400"
              />
              <input
                type="search"
                className="!pl-10"
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setPage(1);
                }}
                placeholder="Tìm mã hóa đơn, người thụ hưởng..."
              />
            </label>
            <label className="sm:w-48">
              <span className="sr-only">Lọc theo trạng thái</span>
              <select
                value={filter}
                onChange={(e) => {
                  setFilter(e.target.value);
                  setPage(1);
                }}
              >
                {filters.map((f) => (
                  <option value={f.value} key={f.value}>
                    {f.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="sm:w-44">
              <span className="sr-only">Sắp xếp</span>
              <select
                value={sort}
                onChange={(event) => {
                  setSort(event.target.value);
                  setPage(1);
                }}
              >
                <option value="recent">Mới nhất trước</option>
                <option value="expiry">Sắp hết hạn trước</option>
              </select>
            </label>
          </div>
          <p role="status" className="mb-3 text-xs font-medium text-slate-500">
            Hiển thị {visible.length} / {items.length} yêu cầu
          </p>
          {visible.length === 0 ? (
            <Feedback
              empty
              emptyTitle={items.length ? "Không tìm thấy yêu cầu" : "Chưa có yêu cầu"}
              emptyMessage={
                items.length
                  ? "Thử từ khóa hoặc bộ lọc khác."
                  : "Bắt đầu bằng cách tạo yêu cầu thanh toán mới."
              }
              action={
                items.length ? (
                  <button type="button" onClick={resetFilters} className="btn-secondary">
                    Xóa bộ lọc
                  </button>
                ) : (
                  <Link href="/payment-requests/new" className="btn-primary">
                    Tạo yêu cầu đầu tiên
                  </Link>
                )
              }
            />
          ) : (
            <>
              <div className="hidden table-wrap md:block">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Hóa đơn</th>
                      <th>Người thụ hưởng</th>
                      <th>Số tiền</th>
                      <th>Ngày tạo</th>
                      <th>Trạng thái</th>
                      <th>
                        <span className="sr-only">Chi tiết</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {paged.map((p) => (
                      <tr key={p.id} className="hover:bg-slate-50">
                        <td className="font-semibold text-slate-900">
                          <Link
                            className="text-teal-700 hover:underline"
                            href={"/payment-requests/" + p.id}
                          >
                            {p.invoice_reference}
                          </Link>
                        </td>
                        <td>
                          {p.beneficiary_name}
                          <span className="mt-1 block text-xs text-slate-500">
                            {p.bank_code} · {p.account_masked}
                          </span>
                        </td>
                        <td className="font-semibold">{formatMoney(p.amount_minor, p.currency)}</td>
                        <td>{new Date(p.created_at).toLocaleDateString("vi-VN")}</td>
                        <td>
                          <StatusBadge status={p.status} />
                        </td>
                        <td>
                          <Link
                            className="font-semibold text-teal-700 hover:underline"
                            href={"/payment-requests/" + p.id}
                          >
                            Xem
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="divide-y divide-slate-100 md:hidden">
                {paged.map((p) => (
                  <Link
                    key={p.id}
                    href={"/payment-requests/" + p.id}
                    className="block rounded-xl py-4 transition-colors first:pt-0 last:pb-0 hover:bg-teal-50/40"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate font-bold text-slate-900">{p.invoice_reference}</p>
                        <p className="muted mt-1 truncate">{p.beneficiary_name}</p>
                      </div>
                      <Icon name="arrowRight" size={18} className="shrink-0 text-slate-400" />
                    </div>
                    <div className="mt-3 flex items-center justify-between gap-3">
                      <span className="font-semibold">
                        {formatMoney(p.amount_minor, p.currency)}
                      </span>
                      <StatusBadge status={p.status} />
                    </div>
                  </Link>
                ))}
              </div>
            </>
          )}
          {pageCount > 1 && (
            <nav
              aria-label="Phân trang"
              className="mt-5 flex items-center justify-between gap-2 border-t border-slate-100 pt-4"
            >
              <span className="text-sm text-slate-500">
                Trang {currentPage} / {pageCount}
              </span>
              <div className="flex gap-2">
                <button
                  type="button"
                  className="btn-secondary !px-3"
                  disabled={currentPage === 1}
                  onClick={() => setPage(currentPage - 1)}
                  aria-label="Trang trước"
                >
                  <Icon name="arrowLeft" size={17} />
                </button>
                <button
                  type="button"
                  className="btn-secondary !px-3"
                  disabled={currentPage === pageCount}
                  onClick={() => setPage(currentPage + 1)}
                  aria-label="Trang tiếp"
                >
                  <Icon name="arrowRight" size={17} />
                </button>
              </div>
            </nav>
          )}
        </div>
      )}
    </Shell>
  );
}
