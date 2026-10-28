"use client";

import { Shell } from "@/components/Shell";
import { Feedback } from "@/components/Feedback";
import { useApiQuery } from "@/lib/useApiQuery";
import type { AuditEvent } from "@/types";

export default function Audit() {
  const { data, error, loading, reload } = useApiQuery<AuditEvent[]>("/audit-events");
  const items = data || [];
  return (
    <Shell
      title="Lịch sử hoạt động"
      description="Các sự kiện quan trọng được ghi lại để đối chiếu và kiểm toán."
    >
      <Feedback
        loading={loading}
        error={error}
        retry={reload}
        empty={!loading && !error && !items.length}
        emptyTitle="Chưa có sự kiện"
      />
      {!loading && !error && items.length > 0 && (
        <div className="card table-wrap !p-0">
          <table className="data-table">
            <thead>
              <tr>
                <th>Thời gian</th>
                <th>Sự kiện</th>
                <th>Đối tượng</th>
                <th>Mã liên kết</th>
                <th>Mã băm</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td>{new Date(item.created_at).toLocaleString("vi-VN")}</td>
                  <td className="font-semibold text-slate-900">
                    {item.event_type.replaceAll("_", " ")}
                  </td>
                  <td>
                    {item.object_type}
                    <span
                      className="mt-1 block max-w-40 truncate font-mono text-xs text-slate-500"
                      title={item.object_id}
                    >
                      {item.object_id}
                    </span>
                  </td>
                  <td className="font-mono text-xs" title={item.correlation_id}>
                    {item.correlation_id.slice(0, 12)}…
                  </td>
                  <td className="font-mono text-xs" title={item.event_hash}>
                    {item.event_hash.slice(0, 12)}…
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Shell>
  );
}
