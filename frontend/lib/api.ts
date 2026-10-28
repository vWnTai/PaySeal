import type { LoginResponse } from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "/api/v1";
let refreshPromise: Promise<boolean> | null = null;

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public code?: "MFA_REQUIRED",
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function session() {
  if (typeof window === "undefined") return { token: "", organizationId: "" };
  return {
    token: localStorage.getItem("payseal_access") || "",
    organizationId: localStorage.getItem("payseal_org") || "",
  };
}

export function saveSession(result: LoginResponse) {
  localStorage.setItem("payseal_access", result.access_token);
  localStorage.setItem("payseal_csrf", result.csrf_token);
}

export function clearSession() {
  for (const key of ["payseal_access", "payseal_org", "payseal_csrf"]) {
    localStorage.removeItem(key);
  }
}

const messages: Record<string, string> = {
  "Live transfers require a numeric account number":
    "Chi tiền VND cần số tài khoản ngân hàng chỉ gồm chữ số, dài từ 4 đến 34 số.",
  "Live transfers require a post-verification signature":
    "Cần tạo và ký lại yêu cầu sau khi hồ sơ doanh nghiệp đã được xét duyệt. Chữ ký demo hoặc chữ ký cũ chưa đủ điều kiện chi tiền thật.",
  "Live payments are not ready":
    "Chưa đủ điều kiện giao dịch thật. Xem mục Kết nối thanh toán để biết phần còn thiếu.",
  "Payment channel is not connected": "Tổ chức chưa kết nối kênh thanh toán phù hợp.",
  "Disconnect the existing channel first": "Hãy ngắt kênh cũ trước khi kết nối tài khoản mới.",
  "Payment channel could not be verified":
    "Chưa xác thực được kênh payOS. Kiểm tra khóa API, tài khoản, tên chủ tài khoản và quyền dịch vụ.",
  "Payment provider is temporarily unavailable":
    "Chưa lấy được kết quả từ nhà cung cấp. Hãy đối soát lại sau; không tạo lệnh thay thế.",
  "Explicit real money confirmation required": "Cần xác nhận rõ đây là lệnh chi tiền thật.",
  "MFA confirmation required": "Nhập mã xác thực mới để xác nhận thao tác.",
  "Live transfer exceeds the configured safety limit":
    "Số tiền vượt hạn mức an toàn do quản trị hệ thống đặt.",
  "Live transfers require a six digit bank BIN":
    "Chi tiền thật yêu cầu mã BIN ngân hàng 6 số. Tạo người thụ hưởng và ký lại yêu cầu với mã đúng.",
  "Payout outcome is still unknown":
    "Nhà cung cấp chưa trả về lệnh khớp. Chưa rõ tiền đã chuyển hay chưa; không gửi lại.",
  "Collection expiry must be between one minute and seven days":
    "Liên kết cần có thời hạn từ 1 phút đến 7 ngày kể từ lúc tạo.",
  "Provider receipt does not match the collection":
    "Kết quả nhà cung cấp không khớp khoản thu. Hệ thống chưa ghi nhận số tiền này.",
  "Provider receipt does not match the transfer":
    "Kết quả nhà cung cấp không khớp lệnh chi. Cần kiểm tra và đối soát, không gửi lại.",
  "Only the current approved verification can be revoked":
    "Chỉ có thể thu hồi hồ sơ được chấp thuận hiện tại. Hãy tải lại danh sách.",
  "Business verification required for transfers":
    "Doanh nghiệp cần có hồ sơ được xét duyệt và còn hiệu lực trước khi tạo lệnh chuyển. Dữ liệu demo không được tính là xác minh thực tế.",
  "Organization is suspended": "Tổ chức đang bị tạm ngưng.",
  "Maker cannot initiate their own transfer":
    "Người tạo yêu cầu không được tự tạo lệnh chuyển cho yêu cầu đó. Hãy nhờ người phê duyệt độc lập.",
  "Only active verified signed payments can be transferred":
    "Chỉ yêu cầu đã ký, chữ ký hợp lệ và còn hiệu lực mới được tạo lệnh chuyển.",
  "Signed payment has expired": "Yêu cầu đã ký đã hết hiệu lực.",
  "Sandbox transfers support VND only": "Chuyển tiền thử nghiệm hiện chỉ hỗ trợ VND.",
  "Live transfers are not configured":
    "Chưa có tích hợp chuyển tiền thật. Hệ thống đã chặn thao tác này.",
  "Transfers are disabled": "Chức năng chuyển tiền đang được tắt.",
  "Platform reviewer permission required":
    "Chức năng này chỉ dành cho người xét duyệt được quản trị hệ thống cấp quyền.",
  "Platform reviewer must enable MFA":
    "Người xét duyệt cần bật xác thực hai bước trong mục Bảo mật.",
  "Reviewer cannot review their own organization":
    "Không được xét duyệt hồ sơ của tổ chức mà bạn là thành viên.",
  "Verification is already pending": "Hồ sơ đang chờ xét duyệt. Không cần gửi lại.",
  "Business is already verified": "Hồ sơ doanh nghiệp đã được xét duyệt và còn hiệu lực.",
  "Business document must be a PDF": "Vui lòng chọn hồ sơ PDF hợp lệ.",
  "Business document is too large": "Hồ sơ quá lớn. Vui lòng chọn PDF tối đa 5 MB.",
  "All verification checks are required":
    "Cần hoàn thành cả ba bước kiểm tra độc lập trước khi chấp thuận hồ sơ.",
  "Verification has already been reviewed": "Hồ sơ đã được xử lý. Hãy tải lại danh sách.",
  "Business document integrity mismatch":
    "Tệp hồ sơ không khớp với bản đã nộp. Không được sử dụng để xét duyệt.",
  "Terminal transfer outcome cannot be changed":
    "Giao dịch đã có kết quả cuối cùng, không thể đổi kết quả hoặc chuyển lại.",
  "Idempotency key was reused with a different request":
    "Mã thao tác đã được dùng cho yêu cầu khác. Hãy tải lại trang.",
  "Organization identity is locked during verification":
    "Không thể thay đổi thông tin doanh nghiệp khi hồ sơ đang chờ xét duyệt.",
  "Invalid credentials": "Email hoặc mật khẩu không đúng.",
  "Email already registered": "Email này đã được đăng ký. Hãy đăng nhập bằng tài khoản hiện có.",
  "MFA code required": "Nhập mã 6 số từ ứng dụng xác thực để tiếp tục.",
  "Invalid MFA code": "Mã xác thực không đúng hoặc đã hết hạn. Hãy thử mã mới.",
  "Recent MFA verification required": "Cần xác thực MFA trước khi thực hiện thao tác này.",
  "Maker cannot approve their own payment": "Người tạo yêu cầu cần một thành viên khác phê duyệt.",
  "Maker cannot reject their own payment": "Người tạo yêu cầu cần một thành viên khác quyết định.",
  "Approver already decided": "Bạn đã phê duyệt yêu cầu này. Hãy đợi các thành viên còn lại.",
  "expires_at must be in the future": "Thời hạn phải nằm trong tương lai.",
  "Payment request not found": "Không tìm thấy yêu cầu thanh toán.",
  "Beneficiary not found": "Không tìm thấy người thụ hưởng.",
  "User not found": "Không tìm thấy tài khoản. Người dùng cần đăng ký trước.",
};

type ErrorDetail = string | { loc?: (string | number)[]; msg?: string }[];
const fieldNames: Record<string, string> = {
  email: "Email",
  password: "Mật khẩu",
  full_name: "Họ tên",
  amount_minor: "Số tiền",
  invoice_reference: "Mã hóa đơn",
  expires_at: "Thời hạn",
  reason: "Lý do",
  comment: "Ghi chú",
  account_number: "Số tài khoản",
  bank_code: "Mã ngân hàng",
  domain: "Tên miền",
};

async function responseError(response: Response) {
  const body = (await response.json().catch(() => null)) as { detail?: ErrorDetail } | null;
  if (typeof body?.detail === "string" && messages[body.detail]) {
    return new ApiError(
      response.status,
      messages[body.detail],
      body.detail === "MFA code required" ? "MFA_REQUIRED" : undefined,
    );
  }
  if (Array.isArray(body?.detail)) {
    const names = [
      ...new Set(body.detail.map((item) => fieldNames[String(item.loc?.at(-1))] || "Thông tin")),
    ];
    return new ApiError(response.status, names.join(", ") + " chưa hợp lệ. Vui lòng kiểm tra lại.");
  }
  const fallback: Record<number, string> = {
    401: "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.",
    403: "Bạn chưa có quyền thực hiện thao tác này.",
    404: "Không tìm thấy dữ liệu hoặc bạn chưa có quyền truy cập.",
    409: "Thao tác chưa phù hợp với trạng thái hiện tại. Hãy tải lại để xem thông tin mới nhất.",
    413: "Tệp quá lớn. Hãy chọn tệp nhỏ hơn.",
    415: "Tệp không phải PDF hợp lệ. Hãy kiểm tra lại định dạng.",
    422: "Thông tin chưa hợp lệ. Vui lòng kiểm tra lại.",
    429: "Bạn thao tác quá nhanh. Hãy đợi một chút rồi thử lại.",
  };
  return new ApiError(
    response.status,
    fallback[response.status] || "Không thể xử lý yêu cầu. Vui lòng thử lại.",
  );
}

async function refreshSession(): Promise<boolean> {
  if (refreshPromise) return refreshPromise;
  const csrf = localStorage.getItem("payseal_csrf");
  if (!csrf) return false;
  refreshPromise = (async () => {
    try {
      const response = await fetch(API_BASE + "/auth/refresh", {
        method: "POST",
        credentials: "include",
        headers: { "X-CSRF-Token": csrf },
      });
      if (!response.ok) return false;
      saveSession((await response.json()) as LoginResponse);
      return true;
    } catch {
      return false;
    } finally {
      refreshPromise = null;
    }
  })();
  return refreshPromise;
}

/** Shared authenticated transport for JSON and PDF responses. */
export async function apiRequest(path: string, init: RequestInit = {}, authenticated = true) {
  const current = session();
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  if (authenticated && current.token) headers.set("Authorization", "Bearer " + current.token);
  if (authenticated && current.organizationId)
    headers.set("X-Organization-ID", current.organizationId);
  const request = () => fetch(API_BASE + path, { ...init, headers, credentials: "include" });
  let response: Response;
  try {
    response = await request();
    if (
      response.status === 401 &&
      response.headers.get("WWW-Authenticate") === "Bearer" &&
      authenticated &&
      current.token
    ) {
      // Another request may have already rotated the token while this one was pending.
      const refreshed = session().token !== current.token || (await refreshSession());
      if (refreshed) {
        headers.set("Authorization", "Bearer " + session().token);
        response = await request();
      }
      if (response.status === 401) {
        clearSession();
        window.dispatchEvent(new Event("payseal:session-expired"));
      }
    }
  } catch (reason) {
    if (init.signal?.aborted) throw reason;
    throw new ApiError(0, "Không kết nối được máy chủ. Hãy kiểm tra mạng và thử lại.");
  }
  if (!response.ok) throw await responseError(response);
  return response;
}

export async function api<T>(
  path: string,
  init: RequestInit = {},
  authenticated = true,
): Promise<T> {
  const response = await apiRequest(path, init, authenticated);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function formatMoney(amount: number, currency: string) {
  const isVnd = currency === "VND";
  return new Intl.NumberFormat("vi-VN", {
    style: "currency",
    currency,
    minimumFractionDigits: isVnd ? 0 : 2,
    maximumFractionDigits: isVnd ? 0 : 2,
  }).format(isVnd ? amount : amount / 100);
}
