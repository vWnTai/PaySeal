export const verificationLabels: Record<string, string> = {
  UNVERIFIED: "Chưa xác minh",
  PENDING: "Chờ xét duyệt",
  APPROVED: "Đã xét duyệt hồ sơ",
  REJECTED: "Hồ sơ bị từ chối",
  CHANGES_REQUESTED: "Cần bổ sung hồ sơ",
  EXPIRED: "Xác minh đã hết hạn",
  STALE: "Thông tin đã thay đổi — cần xác minh lại",
  REVOKED: "Xác minh đã bị thu hồi",
  DEMO_SEEDED: "Dữ liệu demo — chưa xét duyệt thực tế",
};

export const transferLabels: Record<string, string> = {
  SUBMITTED: "Đang chờ kết quả thử nghiệm",
  SUCCEEDED: "Thử nghiệm thành công",
  FAILED: "Thử nghiệm thất bại",
};

export const liveTransferLabels: Record<string, string> = {
  QUEUED: "Đã lưu lệnh — chưa gửi",
  DISPATCHING: "Đang gửi — cần đối soát",
  UNKNOWN: "Chưa rõ kết quả — không gửi lại",
  SUBMITTED: "Nhà cung cấp đang xử lý",
  ON_HOLD: "Nhà cung cấp đang tạm giữ lệnh",
  SUCCEEDED: "Nhà cung cấp xác nhận thành công",
  FAILED: "Lệnh thất bại — không tự gửi lại",
  REVERSED: "Nhà cung cấp báo hoàn trả",
};

export const collectionLabels: Record<string, string> = {
  DISPATCHING: "Đang tạo liên kết",
  UNKNOWN: "Chưa rõ kết quả — cần đối soát",
  PENDING: "Chờ khách thanh toán",
  PROCESSING: "Đang xử lý thanh toán",
  UNDERPAID: "Đã nhận một phần",
  PAID: "Nhà cung cấp xác nhận đã nhận đủ",
  CANCELLED: "Đã hủy liên kết",
  EXPIRED: "Liên kết đã hết hạn",
  FAILED: "Nhà cung cấp báo lỗi",
};

export const readinessLabels: Record<string, string> = {
  LIVE_DISABLED: "Quản trị hệ thống chưa bật giao dịch thật",
  PRODUCTION_REQUIRED: "Cần triển khai môi trường production",
  HTTPS_DOMAIN_REQUIRED: "Cần tên miền công khai và HTTPS",
  SECURE_COOKIE_REQUIRED: "Cần bật cookie bảo mật",
  ENCRYPTION_KEY_REQUIRED: "Cần khóa mã hóa riêng cho production",
  POSTGRES_REQUIRED: "Cần cơ sở dữ liệu PostgreSQL",
  PRODUCTION_SECRETS_REQUIRED: "Cần thay toàn bộ khóa và mật khẩu phát triển",
  TRANSFER_LIMIT_REQUIRED: "Cần đặt hạn mức chi tiền an toàn",
  ORIGIN_HOST_REQUIRED: "Cần cấu hình tên miền trong CORS và danh sách máy chủ tin cậy",
};

export function operationTone(status: string) {
  return status === "APPROVED" || status === "SUCCEEDED"
    ? "border-emerald-200 bg-emerald-50 text-emerald-800"
    : status === "REJECTED" || status === "FAILED" || status === "EXPIRED"
      ? "border-red-200 bg-red-50 text-red-800"
      : "border-amber-200 bg-amber-50 text-amber-900";
}
