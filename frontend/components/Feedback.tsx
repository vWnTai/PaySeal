import { Icon } from "@/components/Icon";
import type { ReactNode } from "react";

export function Feedback({
  loading,
  error,
  empty,
  emptyTitle,
  emptyMessage,
  retry,
  action,
}: {
  loading?: boolean;
  error?: string;
  empty?: boolean;
  emptyTitle?: string;
  emptyMessage?: string;
  retry?: () => void;
  action?: ReactNode;
}) {
  if (loading)
    return (
      <div className="card space-y-3" role="status" aria-label="Đang tải dữ liệu">
        <span className="sr-only">Đang tải dữ liệu, vui lòng đợi.</span>
        <div className="skeleton h-5 w-44 rounded" />
        <div className="skeleton h-4 w-full rounded" />
        <div className="skeleton h-4 w-2/3 rounded" />
      </div>
    );
  if (error)
    return (
      <div role="alert" className="alert-error">
        <Icon name="alert" size={20} />
        <div>
          <strong>Không thể tải dữ liệu</strong>
          <p className="mt-1">{error}</p>
          {retry && (
            <button
              type="button"
              onClick={retry}
              className="mt-3 inline-flex items-center gap-2 font-semibold underline underline-offset-4"
            >
              <Icon name="history" size={16} />
              Thử lại
            </button>
          )}
        </div>
      </div>
    );
  if (empty)
    return (
      <div className="card py-12 text-center">
        <div className="mx-auto mb-4 grid h-12 w-12 place-items-center rounded-2xl bg-teal-50 text-teal-700">
          <Icon name="file" size={24} />
        </div>
        <h2 className="font-semibold text-slate-900">{emptyTitle || "Chưa có dữ liệu"}</h2>
        <p className="muted mt-1">{emptyMessage || "Các mục mới sẽ xuất hiện ở đây."}</p>
        {action && <div className="mt-5">{action}</div>}
      </div>
    );
  return null;
}
