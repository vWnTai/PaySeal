"use client";

import { FormEvent, useEffect, useState } from "react";
import { Shell } from "@/components/Shell";
import { Feedback } from "@/components/Feedback";
import { Icon } from "@/components/Icon";
import { api, session } from "@/lib/api";
import { useApiQuery } from "@/lib/useApiQuery";
import { LoadingButton } from "@/components/LoadingButton";
import type { Member } from "@/types";
const roles = [
  { value: "MAKER", label: "Người tạo" },
  { value: "APPROVER", label: "Người phê duyệt" },
  { value: "AUDITOR", label: "Kiểm toán" },
  { value: "VIEWER", label: "Chỉ xem" },
  { value: "API_CLIENT", label: "API client" },
];
function roleLabel(role: string) {
  return roles.find((r) => r.value === role)?.label || role;
}

export default function Members() {
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [org, setOrg] = useState("");
  useEffect(() => {
    const activeOrg = session().organizationId;
    setOrg(activeOrg);
  }, []);
  const {
    data,
    error: queryError,
    loading,
    reload: load,
  } = useApiQuery<Member[]>(org ? "/organizations/" + org + "/members" : null);
  const items = data || [];
  async function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    const form = event.currentTarget;
    const data = new FormData(event.currentTarget);
    try {
      await api("/organizations/" + org + "/members", {
        method: "POST",
        body: JSON.stringify({ email: data.get("email"), role: data.get("role") }),
      });
      form.reset();
      await load();
      setNotice("Đã thêm thành viên.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không thể thêm thành viên");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Shell title="Thành viên" description="Thêm người dùng đã đăng ký và phân vai trò phù hợp.">
      {error && (
        <div role="alert" className="alert-error mb-5">
          <Icon name="alert" size={20} />
          <span>{error}</span>
        </div>
      )}
      {notice && (
        <div role="status" className="alert-success mb-5">
          <Icon name="check" size={20} />
          <span>{notice}</span>
        </div>
      )}
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_330px]">
        <section className="card">
          <h2 className="section-title">Danh sách thành viên</h2>
          <div className="mt-4">
            <Feedback
              loading={loading}
              error={queryError}
              retry={load}
              empty={!loading && !items.length && !error}
              emptyTitle="Chưa có thành viên"
            />
            {items.map((m) => (
              <div
                className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 py-4"
                key={m.id}
              >
                <div className="flex min-w-0 items-center gap-3">
                  <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-teal-50 font-bold text-teal-700">
                    {m.full_name?.[0]?.toUpperCase() || "?"}
                  </span>
                  <div className="min-w-0">
                    <p className="truncate font-semibold text-slate-900">{m.full_name}</p>
                    <p className="truncate text-sm text-slate-500">{m.email}</p>
                  </div>
                </div>
                <span className="badge border-slate-200 bg-slate-50 text-slate-700">
                  {roleLabel(m.role)}
                </span>
              </div>
            ))}
          </div>
        </section>
        <form onSubmit={add} className="card h-fit space-y-4">
          <div className="flex items-center gap-2">
            <Icon name="users" size={20} className="text-teal-700" />
            <h2 className="section-title">Thêm thành viên</h2>
          </div>
          <p className="muted">Người được thêm cần có tài khoản PaySeal.</p>
          <label>
            <span className="label">Email</span>
            <input name="email" type="email" required placeholder="dongnghiep@congty.vn" />
          </label>
          <label>
            <span className="label">Vai trò</span>
            <select name="role">
              {roles.map((r) => (
                <option value={r.value} key={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
          </label>
          <LoadingButton
            busy={busy}
            busyLabel="Đang thêm..."
            disabled={!org}
            className="btn-primary w-full"
          >
            Thêm thành viên
          </LoadingButton>
        </form>
      </div>
    </Shell>
  );
}
