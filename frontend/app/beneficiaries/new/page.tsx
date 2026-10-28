"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { Shell } from "@/components/Shell";
import { Icon } from "@/components/Icon";
import { api } from "@/lib/api";
import { LoadingButton } from "@/components/LoadingButton";

export default function NewBeneficiary() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(event.currentTarget);
    try {
      await api("/beneficiaries", {
        method: "POST",
        body: JSON.stringify({
          name: data.get("name"),
          bank_code: data.get("bank"),
          account_number: data.get("account"),
        }),
      });
      router.push("/beneficiaries");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không thể thêm người thụ hưởng");
      setBusy(false);
    }
  }
  return (
    <Shell
      title="Thêm người thụ hưởng"
      description="Nhập đúng tên và số tài khoản. Sau khi tạo, số tài khoản không thể sửa trực tiếp."
      action={
        <Link href="/beneficiaries" className="btn-secondary w-full sm:w-auto">
          <Icon name="arrowLeft" size={17} />
          Quay lại
        </Link>
      }
    >
      <form onSubmit={submit} className="card max-w-2xl space-y-5">
        {error && (
          <div role="alert" className="alert-error">
            <Icon name="alert" size={20} />
            <span>{error}</span>
          </div>
        )}
        <label>
          <span className="label">Tên người thụ hưởng</span>
          <input
            name="name"
            required
            minLength={2}
            maxLength={200}
            placeholder="Tên đúng như trên tài khoản ngân hàng"
          />
        </label>
        <label>
          <span className="label">Mã ngân hàng</span>
          <input
            name="bank"
            required
            minLength={2}
            maxLength={32}
            pattern="[A-Za-z0-9_-]+"
            placeholder="Mã BIN 6 số hoặc mã ngân hàng cho thử nghiệm"
          />
          <span className="hint">
            Chi tiền thật cần mã BIN ngân hàng 6 số do nhà cung cấp xác nhận. Mã chữ chỉ dùng cho
            xác minh tài liệu hoặc thử nghiệm.
          </span>
        </label>
        <label>
          <span className="label">Số tài khoản</span>
          <input
            name="account"
            required
            minLength={4}
            maxLength={64}
            pattern="[A-Za-z0-9-]+"
            autoComplete="off"
            placeholder="Nhập số tài khoản"
          />
          <span className="hint">
            Thông tin được mã hóa khi lưu trữ. Hãy kiểm tra kỹ trước khi tiếp tục.
          </span>
        </label>
        <div className="flex flex-col-reverse gap-3 border-t border-slate-100 pt-5 sm:flex-row sm:justify-end">
          <Link href="/beneficiaries" className="btn-secondary">
            Hủy
          </Link>
          <LoadingButton busy={busy} busyLabel="Đang lưu...">
            Thêm người thụ hưởng
          </LoadingButton>
        </div>
      </form>
    </Shell>
  );
}
