import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it("renders a readable state", () => {
    render(<StatusBadge status="PENDING_APPROVAL" />);
    expect(screen.getByText("Chờ phê duyệt")).toBeTruthy();
  });
});
