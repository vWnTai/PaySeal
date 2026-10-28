import { describe, expect, it } from "vitest";
import {
  collectionLabels,
  liveTransferLabels,
  readinessLabels,
  transferLabels,
} from "./operations";

describe("payment presentation", () => {
  it("keeps real and sandbox outcomes distinct", () => {
    expect(transferLabels.SUCCEEDED).toContain("Thử nghiệm");
    expect(liveTransferLabels.SUCCEEDED).toContain("Nhà cung cấp");
    expect(liveTransferLabels.UNKNOWN).toContain("không gửi lại");
  });
  it("does not call a pending receivable paid", () => {
    expect(collectionLabels.PENDING).toContain("Chờ");
    expect(collectionLabels.PAID).toContain("xác nhận");
  });
  it("explains production readiness in Vietnamese", () => {
    expect(readinessLabels.HTTPS_DOMAIN_REQUIRED).toContain("HTTPS");
    expect(readinessLabels.LIVE_DISABLED).toContain("chưa bật");
  });
});
