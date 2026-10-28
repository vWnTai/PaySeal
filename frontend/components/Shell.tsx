"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Icon, type IconName } from "@/components/Icon";
import { api, clearSession, session } from "@/lib/api";
import { Feedback } from "@/components/Feedback";
import { useSession } from "@/components/SessionProvider";

const mainLinks: { href: string; label: string; icon: IconName }[] = [
  { href: "/dashboard", label: "Tổng quan", icon: "grid" },
  { href: "/payment-requests", label: "Yêu cầu thanh toán", icon: "file" },
  { href: "/approvals", label: "Cần phê duyệt", icon: "check" },
  { href: "/beneficiaries", label: "Người thụ hưởng", icon: "wallet" },
  { href: "/collections", label: "Thu tiền", icon: "wallet" },
  { href: "/transfers", label: "Chi tiền", icon: "arrowRight" },
];
const adminLinks: { href: string; label: string; icon: IconName }[] = [
  { href: "/organization", label: "Tổ chức", icon: "building" },
  { href: "/organization/members", label: "Thành viên", icon: "users" },
  { href: "/audit", label: "Lịch sử hoạt động", icon: "history" },
  { href: "/settings/security", label: "Bảo mật", icon: "shield" },
  { href: "/settings/payments", label: "Kết nối thanh toán", icon: "building" },
];

export function Shell({
  title,
  description,
  children,
  action,
}: {
  title: string;
  description?: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  const path = usePathname();
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);
  const { user, organizations, loading, error, reloadUser } = useSession();
  const [selectedOrg, setSelectedOrg] = useState("");
  const sidebar = useRef<HTMLElement>(null);
  const menuButton = useRef<HTMLButtonElement>(null);
  const [loggingOut, setLoggingOut] = useState(false);
  const [mobile, setMobile] = useState(false);

  useEffect(() => {
    const media = window.matchMedia("(max-width: 1023px)");
    const update = () => setMobile(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    setSelectedOrg(session().organizationId);
  }, [user]);

  useEffect(() => {
    if (!menuOpen) return;
    const previousOverflow = document.body.style.overflow;
    const previousFocus = document.activeElement as HTMLElement | null;
    document.body.style.overflow = "hidden";
    const focusable = () =>
      Array.from(
        sidebar.current?.querySelectorAll<HTMLElement>(
          "a[href], button:not([disabled]), select:not([disabled])",
        ) || [],
      ).filter((element) => element.getClientRects().length > 0);
    focusable()[0]?.focus();
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenuOpen(false);
        return;
      }
      if (event.key !== "Tab") return;
      const elements = focusable();
      const first = elements[0];
      const last = elements.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };
    const onResize = () => {
      if (window.innerWidth >= 1024) setMenuOpen(false);
    };
    window.addEventListener("keydown", handleKey);
    window.addEventListener("resize", onResize);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKey);
      window.removeEventListener("resize", onResize);
      (previousFocus || menuButton.current)?.focus();
    };
  }, [menuOpen]);

  async function logout() {
    if (loggingOut) return;
    setLoggingOut(true);
    const csrf = localStorage.getItem("payseal_csrf") || "";
    try {
      await api<void>("/auth/logout", { method: "POST", headers: { "X-CSRF-Token": csrf } }, false);
    } catch {
      /* Local session is still cleared if the API is unavailable. */
    }
    clearSession();
    router.push("/login");
  }

  function switchOrganization(id: string) {
    localStorage.setItem("payseal_org", id);
    setSelectedOrg(id);
    window.location.assign("/dashboard");
  }

  function links(items: typeof mainLinks) {
    return items.map((item) => {
      const active =
        path === item.href || (item.href !== "/organization" && path.startsWith(`${item.href}/`));
      return (
        <Link
          key={item.href}
          href={item.href}
          onClick={() => setMenuOpen(false)}
          aria-current={active ? "page" : undefined}
          className={`nav-item ${active ? "nav-item-active" : ""}`}
        >
          <Icon name={item.icon} size={19} />
          <span>{item.label}</span>
        </Link>
      );
    });
  }

  return (
    <div className="min-h-screen lg:flex">
      <a href="#main-content" className="skip-link">
        Đến nội dung chính
      </a>
      {menuOpen && (
        <button
          type="button"
          aria-label="Đóng menu"
          className="fixed inset-0 z-30 animate-fade-in bg-slate-950/50 backdrop-blur-sm lg:hidden"
          onClick={() => setMenuOpen(false)}
        />
      )}
      <aside
        ref={sidebar}
        id="workspace-navigation"
        aria-label="Menu làm việc"
        role={mobile && menuOpen ? "dialog" : undefined}
        aria-modal={mobile && menuOpen ? true : undefined}
        inert={mobile && !menuOpen ? true : undefined}
        className={`workspace-sidebar fixed inset-y-0 left-0 z-40 flex w-[272px] shrink-0 flex-col text-white transition-transform duration-300 lg:sticky lg:top-0 lg:h-screen lg:translate-x-0 ${menuOpen ? "translate-x-0" : "-translate-x-full"}`}
      >
        <div className="flex items-center justify-between px-6 pb-5 pt-7">
          <Link
            href="/dashboard"
            className="flex items-center gap-3"
            onClick={() => setMenuOpen(false)}
          >
            <span className="grid h-10 w-10 place-items-center rounded-xl bg-teal-400 text-[#102b29]">
              <Icon name="shield" size={25} />
            </span>
            <span>
              <strong className="block text-xl font-extrabold tracking-tight">PaySeal</strong>
              <small className="block text-[10px] font-semibold uppercase tracking-[0.18em] text-teal-200">
                Xác minh thanh toán
              </small>
            </span>
          </Link>
          <button
            type="button"
            className="rounded-lg p-2 text-slate-300 lg:hidden"
            aria-label="Đóng menu"
            onClick={() => setMenuOpen(false)}
          >
            <Icon name="close" />
          </button>
        </div>
        <div className="mx-4 rounded-xl border border-white/10 bg-white/5 p-3">
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-teal-200">
            Không gian làm việc
          </p>
          {organizations.length > 1 ? (
            <select
              className="!border-white/10 !bg-[#173a37] !py-2.5 !text-white"
              aria-label="Chọn tổ chức"
              value={selectedOrg}
              onChange={(e) => switchOrganization(e.target.value)}
            >
              {organizations.map((org) => (
                <option key={org.id} value={org.id}>
                  {org.name}
                </option>
              ))}
            </select>
          ) : (
            <p className="truncate text-sm font-semibold text-white">
              {organizations[0]?.name || (loading ? "Đang tải tổ chức..." : "Chưa chọn tổ chức")}
            </p>
          )}
        </div>
        <nav
          className="mt-6 flex-1 space-y-6 overflow-y-auto px-4 pb-4"
          aria-label="Điều hướng chính"
        >
          <div>
            <p className="mb-2 px-3 text-[11px] font-bold uppercase tracking-widest text-slate-400">
              Công việc
            </p>
            <div className="space-y-1">{links(mainLinks)}</div>
          </div>
          <div>
            <p className="mb-2 px-3 text-[11px] font-bold uppercase tracking-widest text-slate-400">
              Quản lý
            </p>
            <div className="space-y-1">{links(adminLinks)}</div>
            {user?.is_platform_reviewer && (
              <div className="mt-2">
                {links([
                  {
                    href: "/platform/verifications",
                    label: "Xét duyệt doanh nghiệp",
                    icon: "shield",
                  },
                ])}
              </div>
            )}
          </div>
        </nav>
        <div className="border-t border-white/10 p-4">
          <div className="mb-2 flex items-center gap-3 px-2">
            <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-teal-300/15 text-sm font-bold text-teal-100">
              {user?.full_name?.[0]?.toUpperCase() || "P"}
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold">{user?.full_name || "Tài khoản"}</p>
              <p className="truncate text-xs text-slate-400">{user?.email || "PaySeal"}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={logout}
            disabled={loggingOut}
            className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-slate-300 hover:bg-white/10 hover:text-white"
          >
            <Icon name="logout" size={18} />
            {loggingOut ? "Đang đăng xuất..." : "Đăng xuất"}
          </button>
        </div>
      </aside>
      <div className="min-w-0 flex-1" inert={mobile && menuOpen ? true : undefined}>
        <div className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-slate-200/80 bg-white/90 px-4 backdrop-blur sm:px-8 lg:hidden">
          <button
            ref={menuButton}
            type="button"
            className="rounded-lg p-2 text-slate-700"
            aria-label="Mở menu"
            aria-expanded={menuOpen}
            aria-controls="workspace-navigation"
            onClick={() => setMenuOpen(true)}
          >
            <Icon name="menu" />
          </button>
          <span className="text-lg font-extrabold tracking-tight text-[#102b29]">PaySeal</span>
          <Link
            href="/payment-requests/new"
            aria-label="Tạo yêu cầu"
            className="rounded-lg bg-teal-50 p-2 text-teal-700"
          >
            <Icon name="plus" size={19} />
          </Link>
        </div>
        <div className="hidden h-16 items-center justify-between border-b border-slate-200/70 bg-white/60 px-10 lg:flex">
          <span className="flex items-center gap-2 text-xs font-medium text-slate-500">
            <span className="h-1.5 w-1.5 rounded-full bg-teal-500" />
            {organizations.find((org) => org.id === selectedOrg)?.name || "Không gian làm việc"}
          </span>
          <Link href="/settings/security" className="btn-quiet text-xs">
            <Icon name="shield" size={16} />
            {user?.mfa_enabled ? "Đã bật xác thực hai bước" : "Thiết lập bảo mật"}
          </Link>
        </div>
        <main
          id="main-content"
          tabIndex={-1}
          className="page-enter mx-auto w-full max-w-[1440px] px-4 pb-16 pt-7 outline-none sm:px-8 sm:pt-9 lg:px-10"
        >
          <header className="mb-7 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
            <div className="min-w-0">
              <p className="eyebrow mb-2">PAYSEAL · KHÔNG GIAN LÀM VIỆC</p>
              <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-[32px]">
                {title}
              </h1>
              {description && <p className="muted mt-2 max-w-2xl">{description}</p>}
            </div>
            {action && <div className="shrink-0">{action}</div>}
          </header>
          {loading && !user ? (
            <Feedback loading />
          ) : error && !user ? (
            <Feedback error={error} retry={reloadUser} />
          ) : user &&
            !selectedOrg &&
            !path.startsWith("/platform/") &&
            !["/organization", "/settings/security"].includes(path) ? (
            <section className="card py-12 text-center">
              <Icon name="building" size={32} className="mx-auto text-teal-700" />
              <h2 className="section-title mt-4">Bắt đầu bằng một tổ chức</h2>
              <p className="muted mt-2">
                Tạo không gian làm việc để quản lý yêu cầu và người thụ hưởng.
              </p>
              <Link href="/organization" className="btn-primary mt-5">
                Tạo tổ chức <Icon name="arrowRight" size={17} />
              </Link>
            </section>
          ) : (
            children
          )}
        </main>
      </div>
    </div>
  );
}
