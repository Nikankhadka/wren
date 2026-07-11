import { describe, expect, it } from "vitest";
import { formatCents } from "./money";

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
