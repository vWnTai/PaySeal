import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api";
import Login from "./page";

const mocks = vi.hoisted(() => ({ api: vi.fn(), saveSession: vi.fn(), push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: mocks.push }) }));
vi.mock("@/lib/api", async (original) => ({
  ...(await original<typeof import("@/lib/api")>()),
  api: mocks.api,
  saveSession: mocks.saveSession,
}));

const tokens = { access_token: "verified-token", csrf_token: "csrf" };
const me = { organizations: [{ id: "org-a" }] };

function enterCredentials() {
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "user@example.com" } });
  fireEvent.change(screen.getByLabelText("Mật khẩu"), { target: { value: "Strong-password!" } });
  fireEvent.click(screen.getByRole("button", { name: "Đăng nhập" }));
}

async function enterMfaStep() {
  mocks.api.mockRejectedValueOnce(new ApiError(401, "Nhập mã 6 số", "MFA_REQUIRED"));
  render(<Login />);
  enterCredentials();
  return screen.findByLabelText("Mã xác thực");
}

beforeEach(() => {
  vi.resetAllMocks();
  localStorage.clear();
});
afterEach(cleanup);

describe("automatic MFA login", () => {
  it("routes independent platform reviewers to their review workspace", async () => {
    mocks.api
      .mockResolvedValueOnce(tokens)
      .mockResolvedValueOnce({ organizations: [], is_platform_reviewer: true });
    render(<Login />);
    enterCredentials();
    await waitFor(() => expect(mocks.push).toHaveBeenCalledWith("/platform/verifications"));
  });
  it("starts with credentials only and signs non-MFA accounts straight in", async () => {
    mocks.api.mockResolvedValueOnce(tokens).mockResolvedValueOnce(me);
    render(<Login />);
    expect(screen.queryByLabelText("Mã xác thực")).toBeNull();
    expect(screen.queryByText("Tài khoản đã bật xác thực hai bước?")).toBeNull();
    enterCredentials();
    await waitFor(() => expect(mocks.push).toHaveBeenCalledWith("/dashboard"));
    expect(mocks.saveSession).toHaveBeenCalledWith(tokens);
    expect(JSON.parse(mocks.api.mock.calls[0][1].body)).toEqual({
      email: "user@example.com",
      password: "Strong-password!",
    });
  });

  it("opens a focused MFA step without saving tokens or credentials to storage", async () => {
    const input = await enterMfaStep();
    expect(document.activeElement).toBe(input);
    expect(screen.queryByLabelText("Mật khẩu")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(mocks.api).toHaveBeenCalledTimes(1);
    expect(mocks.saveSession).not.toHaveBeenCalled();
    expect(mocks.push).not.toHaveBeenCalled();
    expect(localStorage.length).toBe(0);
    expect(
      (screen.getByRole("button", { name: "Xác nhận và đăng nhập" }) as HTMLButtonElement).disabled,
    ).toBe(true);

    mocks.api.mockResolvedValueOnce(tokens).mockResolvedValueOnce(me);
    fireEvent.change(input, { target: { value: "123 456" } });
    expect((input as HTMLInputElement).value).toBe("123456");
    fireEvent.click(screen.getByRole("button", { name: "Xác nhận và đăng nhập" }));
    await waitFor(() => expect(mocks.push).toHaveBeenCalledWith("/dashboard"));
    expect(JSON.parse(mocks.api.mock.calls[1][1].body)).toEqual({
      email: "user@example.com",
      password: "Strong-password!",
      totp_code: "123456",
    });
    expect(mocks.saveSession).toHaveBeenCalledTimes(1);
  });

  it("keeps incorrect passwords on the credentials step", async () => {
    mocks.api.mockRejectedValueOnce(new ApiError(401, "Email hoặc mật khẩu không đúng."));
    render(<Login />);
    enterCredentials();
    expect((await screen.findByRole("alert")).textContent).toContain("mật khẩu không đúng");
    expect(screen.queryByLabelText("Mã xác thực")).toBeNull();
    expect(mocks.saveSession).not.toHaveBeenCalled();
  });

  it("allows retrying an incorrect MFA code without starting a session", async () => {
    const input = await enterMfaStep();
    mocks.api.mockRejectedValueOnce(new ApiError(401, "Mã xác thực không đúng hoặc đã hết hạn."));
    fireEvent.change(input, { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "Xác nhận và đăng nhập" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Mã xác thực không đúng");
    expect(screen.getByLabelText("Mã xác thực")).toBeTruthy();
    expect(mocks.saveSession).not.toHaveBeenCalled();
    expect(mocks.push).not.toHaveBeenCalled();

    mocks.api.mockResolvedValueOnce(tokens).mockResolvedValueOnce({ organizations: [] });
    fireEvent.change(input, { target: { value: "654321" } });
    fireEvent.click(screen.getByRole("button", { name: "Xác nhận và đăng nhập" }));
    await waitFor(() => expect(mocks.push).toHaveBeenCalledWith("/organization"));
  });

  it("clears the password and MFA input when going back to switch accounts", async () => {
    const input = await enterMfaStep();
    fireEvent.change(input, { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "Quay lại đăng nhập" }));
    expect(screen.queryByLabelText("Mã xác thực")).toBeNull();
    expect((screen.getByLabelText("Mật khẩu") as HTMLInputElement).value).toBe("");
    expect((screen.getByLabelText("Email") as HTMLInputElement).value).toBe("user@example.com");
    expect(mocks.saveSession).not.toHaveBeenCalled();
  });
});
