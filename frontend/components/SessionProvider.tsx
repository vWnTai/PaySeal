"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { api, session } from "@/lib/api";
import { useApiQuery } from "@/lib/useApiQuery";
import type { Organization, User } from "@/types";

type SessionContextValue = {
  user: User | null;
  organizations: Organization[];
  loading: boolean;
  error: string;
  reloadUser: () => Promise<void>;
};
const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const privatePage =
    !["/", "/login", "/register"].includes(pathname) && !pathname.startsWith("/r/");
  const {
    data: user,
    loading,
    error,
    reload: reloadUser,
  } = useApiQuery<User>(privatePage ? "/auth/me" : null);
  const [organizations, setOrganizations] = useState<Organization[]>([]);

  useEffect(() => {
    if (privatePage && !session().token) router.replace("/login");
  }, [privatePage, router]);

  useEffect(() => {
    const expired = () => router.replace("/login");
    window.addEventListener("payseal:session-expired", expired);
    return () => window.removeEventListener("payseal:session-expired", expired);
  }, [router]);

  useEffect(() => {
    const controller = new AbortController();
    if (!user) {
      setOrganizations([]);
      return;
    }
    void Promise.all(
      user.organizations.map(({ id }) =>
        api<Organization>("/organizations/" + id, { signal: controller.signal }),
      ),
    )
      .then((values) => {
        if (!controller.signal.aborted) setOrganizations(values);
      })
      .catch(() => {
        /* Main page reports access errors; do not invent organization names. */
      });
    return () => controller.abort();
  }, [user]);

  return (
    <SessionContext.Provider value={{ user, organizations, loading, error, reloadUser }}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSession() {
  const context = useContext(SessionContext);
  if (!context) throw new Error("useSession must be used inside SessionProvider.");
  return context;
}
