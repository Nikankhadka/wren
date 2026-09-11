import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

/**
 * The theme contract test: pins the approved Airbnb palette and proves every
 * foreground/background pair the design relies on clears WCAG AA. Raw hex
 * lives here by design - this file is where the approved values are named
 * and checked, and it is allowlisted in scripts/check-tokens.mjs.
 */

const css = readFileSync(new URL("./theme.css", import.meta.url), "utf8");

/** Comments name tokens too (`--neutral-94: ...`), so they cannot be parsed. */
const source = css.replace(/\/\*[\s\S]*?\*\//g, "");

const declarations = new Map<string, string>();
for (const match of source.matchAll(/--([\w-]+)\s*:\s*([^;]+);/g)) {
  declarations.set(match[1], match[2].trim());
}

/** Follow a single `var(--x)` reference (Layer 2 maps Layer 1 primitives). */
function resolve(name: string): string {
  const raw = declarations.get(name);
  if (raw === undefined) throw new Error(`theme.css is missing --${name}`);
  const reference = /^var\(--([\w-]+)\)$/.exec(raw);
  return reference ? resolve(reference[1]) : raw;
}

function parseHex(hex: string): [number, number, number] {
  const value = Number.parseInt(hex.slice(1), 16);
  return [(value >> 16) & 0xff, (value >> 8) & 0xff, value & 0xff];
}

function relativeLuminance(hex: string): number {
  const linear = (channel: number) => {
    const c = channel / 255;
    return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  };
  const [r, g, b] = parseHex(hex);
  return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b);
}

/** WCAG 2.x contrast ratio between two #RRGGBB colors. */
function contrastRatio(a: string, b: string): number {
  const la = relativeLuminance(a);
  const lb = relativeLuminance(b);
  const [lighter, darker] = la >= lb ? [la, lb] : [lb, la];
  return (lighter + 0.05) / (darker + 0.05);
}

const APPROVED: Record<string, string> = {
  // Layer 1: the full primary ramp + the channel triple the alpha ladder uses.
  "primary-20": "#8C0026",
  "primary-30": "#B4004E",
  "primary-35": "#E31C5F",
  "primary-40": "#FF385C",
  "primary-45": "#FF5A5F",
  "primary-60": "#FF7A85",
  "primary-70": "#FF99A2",
  "primary-80": "#FFB3BA",
  "primary-90": "#FFD1DA",
  "primary-95": "#FFE8ED",
  "primary-40-rgb": "255 56 92",

  // Layer 2: semantic mappings, resolved through Layer 1.
  "color-bg": "#FFFFFF",
  "color-surface": "#FFFFFF",
  "color-surface-sunken": "#F7F7F7",
  "color-surface-container": "#F0F0F0",
  "color-surface-container-high": "#EBEBEB",
  "color-border": "#DDDDDD",
  "color-border-strong": "#767676",
  "color-text": "#222222",
  "color-text-secondary": "#717171",
  "color-text-tertiary": "#767676",
  "color-text-inverse": "#FFFFFF",
  "color-accent": "#FF385C",
  "color-accent-hover": "#E31C5F",
  "color-accent-active": "#B4004E",
  "color-accent-subtle": "#FFD1DA",
  "color-accent-container": "#FFD1DA",
  "color-focus-ring": "#FF385C",
  "color-success": "#007A04",
  "color-success-subtle": "#E6F5E7",
  "color-warning": "#8A5A00",
  "color-warning-subtle": "#FFF3D6",
  "color-danger": "#C13515",
  "color-danger-subtle": "#FDEDEA",
  "color-info": "#007A7F",
  "color-info-subtle": "#E6F4F5",
  "color-bubble-out": "#E31C5F",
  "color-bubble-in": "#F7F7F7",
  "color-bubble-agent-in": "#FFD1DA",
  "color-highlight": "#FFB400",
};

describe("Airbnb token contract", () => {
  it.each(Object.entries(APPROVED))("--%s is %s", (name, value) => {
    expect(resolve(name)).toBe(value);
  });

  it("gradient-brand keeps all three locked stops", () => {
    const gradient = resolve("gradient-brand");
    expect(gradient).toContain("#E61E4D");
    expect(gradient).toContain("#E31C5F");
    expect(gradient).toContain("#D70466");
  });

  it("gradient-veil keeps the locked bottom stop and fades the top", () => {
    const gradient = resolve("gradient-veil");
    expect(gradient).toContain("#FFD1DA");
    expect(gradient).toContain("rgb(255 232 237 / 0)");
  });
});

const AA = 4.5;
const AA_NON_TEXT = 3;

describe("WCAG AA text pairs", () => {
  const AA_PAIRS: Array<[string, string]> = [
    ["color-text", "color-bg"],
    ["color-text", "color-surface"],
    ["color-text-secondary", "color-bg"],
    ["color-text-secondary", "color-surface"],
    ["color-text-secondary", "color-surface-sunken"],
    ["color-text-tertiary", "color-surface"],
    ["color-text-tertiary", "color-bg"],
    ["color-text-inverse", "color-accent-hover"],
    ["color-text-inverse", "color-accent-active"],
    ["color-text-inverse", "color-danger"],
    ["color-text-inverse", "color-bubble-out"],
    ["color-accent-active", "color-accent-subtle"],
    ["color-accent-active", "color-bubble-agent-in"],
    ["color-text", "color-bubble-agent-in"],
    ["color-text", "color-bubble-in"],
    ["color-text", "color-highlight"],
    ["color-success", "color-success-subtle"],
    ["color-warning", "color-warning-subtle"],
    ["color-danger", "color-danger-subtle"],
    ["color-info", "color-info-subtle"],
  ];

  it.each(AA_PAIRS)("%s on %s clears AA", (foreground, background) => {
    const ratio = contrastRatio(resolve(foreground), resolve(background));
    expect(
      ratio,
      `${foreground} on ${background} = ${ratio.toFixed(2)}:1`
    ).toBeGreaterThanOrEqual(AA);
  });

  it("every CTA gradient stop clears AA with inverse text", () => {
    const stops = resolve("gradient-brand").match(/#[0-9A-F]{6}/gi) ?? [];
    expect(stops).toHaveLength(3);
    for (const stop of stops) {
      const ratio = contrastRatio(stop, resolve("color-text-inverse"));
      expect(ratio, `${stop} with inverse text = ${ratio.toFixed(2)}:1`).toBeGreaterThanOrEqual(AA);
    }
  });
});

describe("WCAG non-text borders", () => {
  it.each([
    ["color-border-strong", "color-surface"],
    ["color-border-strong", "color-bg"],
  ])("%s on %s clears 3:1", (foreground, background) => {
    const ratio = contrastRatio(resolve(foreground), resolve(background));
    expect(
      ratio,
      `${foreground} on ${background} = ${ratio.toFixed(2)}:1`
    ).toBeGreaterThanOrEqual(AA_NON_TEXT);
  });
});
