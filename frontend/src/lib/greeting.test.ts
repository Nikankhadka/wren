import { describe, expect, it } from "vitest";
import { customerOpening } from "./greeting";

const IDENTITY = "Hi, I'm ByteFix Repairs's assistant. How can I help today?";

describe("customerOpening", () => {
  it("opens with the identity line when nothing is configured", () => {
    expect(customerOpening("ByteFix Repairs", null)).toBe(IDENTITY);
    expect(customerOpening("ByteFix Repairs", "   ")).toBe(IDENTITY);
  });

  it("drops a configured greeting identical to the one it composes", () => {
    expect(customerOpening("ByteFix Repairs", IDENTITY)).toBe(IDENTITY);
  });

  it("drops the greeting the frontend used to compose itself", () => {
    const previous = "Hi! How can I help you with ByteFix Repairs today?";
    expect(customerOpening("ByteFix Repairs", previous)).toBe(IDENTITY);
  });

  it("drops a near-identical greeting that only says hello again", () => {
    expect(customerOpening("ByteFix Repairs", "Hello there! Welcome to ByteFix Repairs.")).toBe(
      IDENTITY,
    );
  });

  it("keeps the sentences a configured greeting actually adds", () => {
    const configured =
      "Hi! Welcome to ByteFix Repairs. I can quote a repair, check on an existing " +
      "ticket, or answer questions about our services - what can I do for you?";
    expect(customerOpening("ByteFix Repairs", configured)).toBe(
      `${IDENTITY} I can quote a repair, check on an existing ticket, or answer ` +
        "questions about our services - what can I do for you?",
    );
  });

  it("never says hello twice", () => {
    const openings = [
      null,
      IDENTITY,
      "Hi there!",
      "Hi! Welcome to ByteFix Repairs. We fix phones while you wait.",
      "Hello, and welcome. Ask us anything about repairs.",
    ].map((greeting) => customerOpening("ByteFix Repairs", greeting));
    for (const opening of openings) {
      expect(opening.startsWith(IDENTITY)).toBe(true);
      expect(opening.toLowerCase().split(/\bhi\b|\bhello\b|\bhey\b/).length).toBe(2);
    }
  });
});
