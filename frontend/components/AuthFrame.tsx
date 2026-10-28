import type { ReactNode } from "react";
import { Icon } from "@/components/Icon";

export function AuthFrame({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <main className="grid min-h-screen lg:grid-cols-[minmax(0,1fr)_minmax(460px,0.9fr)]">
      <section className="relative hidden overflow-hidden bg-[#102b29] p-10 text-white lg:flex lg:flex-col lg:justify-between xl:p-14">
        <div className="auth-orb absolute -right-24 -top-24 h-96 w-96 rounded-full border border-white/10 bg-white/5" />
        <div className="auth-orb absolute -bottom-44 -left-24 h-[460px] w-[460px] rounded-full border border-white/10 bg-teal-400/10" />
        <div className="relative flex items-center gap-3">
          <span className="grid h-11 w-11 place-items-center rounded-xl bg-teal-400 text-[#102b29]">
            <Icon name="shield" size={26} />
          </span>
          <span className="text-2xl font-extrabold tracking-tight">PaySeal</span>
        </div>
        <div className="relative max-w-xl">
          <span className="inline-flex items-center gap-2 rounded-full border border-teal-300/25 bg-teal-300/10 px-3 py-1.5 text-xs font-semibold text-teal-200">
            <Icon name="lock" size={15} /> Xác minh thanh toán an toàn
          </span>
          <h2 className="mt-6 text-4xl font-bold leading-tight tracking-tight xl:text-5xl">
            Rõ ràng từng bước.
            <br />
            <span className="text-teal-300">An tâm khi thanh toán.</span>
          </h2>
          <p className="mt-5 max-w-md text-base leading-relaxed text-slate-300">
            Tạo yêu cầu, phê duyệt, ký số và xác minh tài liệu trong một quy trình dễ theo dõi.
          </p>
          <div className="stagger mt-10 grid max-w-md gap-4 sm:grid-cols-3">
            {[
              ["01", "Tạo yêu cầu"],
              ["02", "Phê duyệt"],
              ["03", "Xác minh"],
            ].map(([num, label]) => (
              <div className="rounded-xl border border-white/10 bg-white/5 p-4" key={num}>
                <p className="text-xl font-bold text-teal-300">{num}</p>
                <p className="mt-2 text-sm font-medium">{label}</p>
              </div>
            ))}
          </div>
        </div>
        <p className="relative text-xs text-slate-400">
          PaySeal · Nền tảng xác minh yêu cầu thanh toán
        </p>
      </section>
      <section className="flex min-h-screen items-center justify-center p-5 sm:p-10">
        <div className="page-enter w-full max-w-md">
          <div className="mb-8 lg:hidden">
            <span className="inline-flex items-center gap-2 text-xl font-extrabold text-[#102b29]">
              <span className="grid h-9 w-9 place-items-center rounded-lg bg-teal-600 text-white">
                <Icon name="shield" size={21} />
              </span>
              PaySeal
            </span>
          </div>
          <div className="mb-7">
            <p className="eyebrow">Chào mừng đến với PaySeal</p>
            <h1 className="mt-2 text-3xl font-bold tracking-tight text-slate-900">{title}</h1>
            <p className="muted mt-2">{description}</p>
          </div>
          {children}
        </div>
      </section>
    </main>
  );
}
