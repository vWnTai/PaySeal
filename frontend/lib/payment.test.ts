import { describe, expect, it } from "vitest";
import { normalizeSearch, toMinorUnits } from "./payment";

describe("money inputs", () => {
  it("preserves whole VND amounts and exact USD cents", () => {
    expect(toMinorUnits("28500000", "VND")).toBe(28_500_000);
    expect(toMinorUnits("100.50", "USD")).toBe(10_050);
    expect(toMinorUnits("0.29", "USD")).toBe(29);
    expect(toMinorUnits("1", "USD")).toBe(100);
  });

  it.each(["0", "-1", "1.5", "1e3", "9000000000000001"])("rejects invalid VND: %s", (value) => {
    expect(() => toMinorUnits(value, "VND")).toThrow();
  });

  it("rejects excess decimal precision instead of silently changing the amount", () => {
    expect(() => toMinorUnits("1.999", "USD")).toThrow();
  });
});

it("matches Vietnamese names without accents, including đ", () => {
  expect(normalizeSearch("  Đặng Thị Ánh  ")).toBe("dang thi anh");
});
