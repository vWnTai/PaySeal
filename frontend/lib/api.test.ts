import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, apiRequest, session } from "./api";

function json(body: unknown, status = 200, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), { status, headers });
}
const expired = () =>
  json({ detail: "Invalid or expired access token" }, 401, { "WWW-Authenticate": "Bearer" });

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("payseal_access", "old-token");
  localStorage.setItem("payseal_csrf", "csrf");
  localStorage.setItem("payseal_org", "org-a");
});
afterEach(() => vi.unstubAllGlobals());

describe("API transport", () => {
  it("identifies the MFA challenge independently of its translated message", async () => {
    const fetch = vi.fn().mockResolvedValue(json({ detail: "MFA code required" }, 401));
    vi.stubGlobal("fetch", fetch);
    await expect(api("/auth/login", { method: "POST" }, false)).rejects.toMatchObject({
      status: 401,
      code: "MFA_REQUIRED",
    });
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("translates validation details into actionable messages", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          json({ detail: [{ loc: ["body", "amount_minor"], msg: "bad input" }] }, 422),
        ),
    );
    await expect(api("/payment-requests")).rejects.toThrow("Số tiền chưa hợp lệ");
  });

  it("sends public verification requests without account or organization headers", async () => {
    const fetch = vi.fn().mockResolvedValue(json({ status: "VERIFIED" }));
    vi.stubGlobal("fetch", fetch);
    await api("/public/verify/token", {}, false);
    const headers = fetch.mock.calls[0][1].headers as Headers;
    expect(headers.has("Authorization")).toBe(false);
    expect(headers.has("X-Organization-ID")).toBe(false);
  });

  it("coordinates concurrent refresh and preserves the original request on retry", async () => {
    let finishRefresh!: (response: Response) => void;
    const refresh = new Promise<Response>((resolve) => {
      finishRefresh = resolve;
    });
    const fetch = vi.fn().mockImplementation((url: string, init: RequestInit) => {
      if (url.endsWith("/auth/refresh")) return refresh;
      return Promise.resolve(
        new Headers(init.headers).get("Authorization") === "Bearer old-token"
          ? expired()
          : json({ ok: true }),
      );
    });
    vi.stubGlobal("fetch", fetch);
    const requests = [
      api("/payment-requests/sign", {
        method: "POST",
        headers: { "Idempotency-Key": "stable" },
        body: '{"totp_code":"123456"}',
      }),
      api("/auth/me"),
    ];
    await vi.waitFor(() =>
      expect(fetch.mock.calls.filter(([url]) => url.endsWith("/auth/refresh"))).toHaveLength(1),
    );
    finishRefresh(json({ access_token: "new-token", csrf_token: "new-csrf" }));
    await Promise.all(requests);
    expect(session().token).toBe("new-token");
    const calls = fetch.mock.calls.filter(([url]) => url.endsWith("/payment-requests/sign"));
    expect(calls).toHaveLength(2);
    expect(calls[1][1].body).toBe('{"totp_code":"123456"}');
    expect(new Headers(calls[1][1].headers).get("Idempotency-Key")).toBe("stable");
  });

  it("does not treat an incorrect MFA code as an expired session", async () => {
    const fetch = vi.fn().mockResolvedValue(json({ detail: "Invalid MFA code" }, 401));
    vi.stubGlobal("fetch", fetch);
    await expect(api("/payment-requests/id/approve")).rejects.toThrow("Mã xác thực");
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(session().token).toBe("old-token");
  });

  it("clears an expired session when refresh fails", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(expired())
      .mockResolvedValueOnce(json({ detail: "Invalid refresh token" }, 401));
    vi.stubGlobal("fetch", fetch);
    await expect(api("/auth/me")).rejects.toThrow("Phiên đăng nhập");
    expect(session()).toEqual({ token: "", organizationId: "" });
  });

  it("uses the same tenant-aware transport for PDF downloads", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(
        new Response("%PDF-1.7", { headers: { "Content-Type": "application/pdf" } }),
      );
    vi.stubGlobal("fetch", fetch);
    const response = await apiRequest("/payment-requests/id/pdf");
    expect(await response.text()).toBe("%PDF-1.7");
    expect(new Headers(fetch.mock.calls[0][1].headers).get("X-Organization-ID")).toBe("org-a");
  });
});
