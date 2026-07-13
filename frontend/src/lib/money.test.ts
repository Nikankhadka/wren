import { describe, expect, it } from "vitest";
import { formatCents, formatUsd } from "./money";

describe("formatCents", () => {
  it("formats whole dollars", () => {
    expect(formatCents(12000)).toBe("$120.00");
  });

  it("formats cents remainders", () => {
    expect(formatCents(12960)).toBe("$129.60");
  });

  it("formats thousands with separators", () => {
    expect(formatCents(129900)).toBe("$1,299.00");
  });

  it("formats zero", () => {
    expect(formatCents(0)).toBe("$0.00");
  });

  it("formats single cents", () => {
    expect(formatCents(7)).toBe("$0.07");
  });
});

describe("formatUsd", () => {
  it("formats whole dollars", () => {
    expect(formatUsd(120)).toBe("$120.00");
  });

  it("formats a cents remainder", () => {
    expect(formatUsd(129.6)).toBe("$129.60");
  });

  it("formats thousands with separators", () => {
    expect(formatUsd(1299)).toBe("$1,299.00");
  });

  it("formats zero", () => {
    expect(formatUsd(0)).toBe("$0.00");
  });

  it("formats a small amount", () => {
    expect(formatUsd(0.5)).toBe("$0.50");
  });

  it("keeps sub-cent precision for trace costs", () => {
    expect(formatUsd(0.0012)).toBe("$0.0012");
  });
});
