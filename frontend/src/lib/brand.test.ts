import { describe, expect, it } from "vitest";
import { brandStyle, contrastRatio, deriveBrandVars, parseHex, SURFACE_LIGHT } from "./brand";

describe("parseHex", () => {
  it("parses #RRGGBB", () => {
    expect(parseHex("#D97757")).toEqual([0xd9, 0x77, 0x57]);
    expect(parseHex("  #ffffff ")).toEqual([255, 255, 255]);
  });

  it("rejects everything else", () => {
    for (const bad of ["", "D97757", "#fff", "#GGGGGG", "#D9775", "#D977577", "red"]) {
      expect(parseHex(bad)).toBeNull();
    }
  });
});

describe("contrastRatio", () => {
  it("is 21 for black on white and 1 for identical colors", () => {
    expect(contrastRatio("#000000", "#FFFFFF")).toBeCloseTo(21, 1);
    expect(contrastRatio("#D97757", "#D97757")).toBeCloseTo(1, 5);
  });

  it("is symmetric", () => {
    expect(contrastRatio("#2D6A4F", "#FFFFFF")).toBeCloseTo(contrastRatio("#FFFFFF", "#2D6A4F"), 8);
  });

  it("returns 0 on invalid input", () => {
    expect(contrastRatio("nope", "#FFFFFF")).toBe(0);
  });
});

describe("deriveBrandVars", () => {
  it("derives a full step set from a dark, AA-passing accent", () => {
    const vars = deriveBrandVars("#2D6A4F");
    expect(vars).not.toBeNull();
    expect(vars?.accent).toBe("#2D6A4F");
    expect(vars?.focusRing).toBe("#2D6A4F");
    // hover/active step progressively darker, subtle is a near-white wash
    expect(contrastRatio(vars!.accentHover, "#FFFFFF")).toBeGreaterThan(
      contrastRatio(vars!.accent, "#FFFFFF")
    );
    expect(contrastRatio(vars!.accentActive, "#FFFFFF")).toBeGreaterThan(
      contrastRatio(vars!.accentHover, "#FFFFFF")
    );
    expect(contrastRatio(vars!.accentSubtle, "#FFFFFF")).toBeLessThan(1.3);
  });

  it("falls back (null) when contrast vs the light surface fails AA", () => {
    // #D97757 is ~3.1:1 on white - readable as a wash, not as text-on-accent.
    expect(contrastRatio("#D97757", SURFACE_LIGHT)).toBeLessThan(4.5);
    expect(deriveBrandVars("#D97757")).toBeNull();
    expect(deriveBrandVars("#FFFF00")).toBeNull();
  });

  it("falls back (null) on missing or malformed accents", () => {
    expect(deriveBrandVars(undefined)).toBeNull();
    expect(deriveBrandVars(42)).toBeNull();
    expect(deriveBrandVars("not-a-color")).toBeNull();
  });
});

describe("brandStyle", () => {
  it("emits a light-mode-scoped override for a valid accent", () => {
    const css = brandStyle({ accent: "#2D6A4F" });
    expect(css).toContain("--color-accent:#2D6A4F;");
    expect(css).toContain("--color-focus-ring:#2D6A4F;");
    expect(css).toContain("@media (prefers-color-scheme: light)");
    expect(css).toContain(':root[data-theme="light"]');
    // never an unscoped :root override - it would poison dark mode
    expect(css).not.toMatch(/(^|})\s*:root\s*\{/);
  });

  it("returns null when the accent is absent or fails the gate", () => {
    expect(brandStyle({})).toBeNull();
    expect(brandStyle({ accent: "#FFFF00" })).toBeNull();
    expect(brandStyle({ accent: "#D97757" })).toBeNull();
  });
});
