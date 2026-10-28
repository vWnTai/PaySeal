export const paymentStatuses = [
  { value: "DRAFT", label: "Bản nháp", classes: "border-slate-200 bg-slate-100 text-slate-700" },
  {
    value: "PENDING_APPROVAL",
    label: "Chờ phê duyệt",
    classes: "border-amber-200 bg-amber-50 text-amber-800",
  },
  { value: "APPROVED", label: "Đã phê duyệt", classes: "border-sky-200 bg-sky-50 text-sky-800" },
  { value: "SIGNED", label: "Đã ký", classes: "border-teal-200 bg-teal-50 text-teal-800" },
  { value: "REVOKED", label: "Đã thu hồi", classes: "border-red-200 bg-red-50 text-red-800" },
  { value: "EXPIRED", label: "Hết hạn", classes: "border-red-200 bg-red-50 text-red-800" },
  {
    value: "SUPERSEDED",
    label: "Đã thay thế",
    classes: "border-slate-200 bg-slate-100 text-slate-700",
  },
  { value: "REJECTED", label: "Bị từ chối", classes: "border-red-200 bg-red-50 text-red-800" },
  { value: "VERIFIED", label: "Đã xác minh", classes: "border-teal-200 bg-teal-50 text-teal-800" },
];

export function normalizeSearch(value: string) {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/gi, "d")
    .toLowerCase()
    .trim();
}

export function localDateTime(date: Date) {
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

/** Parses decimal money without rounding binary floating-point values. */
export function toMinorUnits(value: string, currency: string) {
  const digits = currency === "VND" ? 0 : 2;
  const pattern = digits === 0 ? /^\d+$/ : /^\d+(?:\.\d{1,2})?$/;
  if (!pattern.test(value)) throw new Error("Số tiền không hợp lệ.");
  const [whole, fraction = ""] = value.split(".");
  const amount = Number(whole) * 10 ** digits + Number(fraction.padEnd(digits, "0"));
  if (!Number.isSafeInteger(amount) || amount <= 0 || amount > 9_000_000_000_000_000) {
    throw new Error("Số tiền phải lớn hơn 0 và nằm trong giới hạn cho phép.");
  }
  return amount;
}
