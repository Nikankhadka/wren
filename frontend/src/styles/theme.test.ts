import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

/**
 * The theme contract test: pins the approved Soft Sakura palette and proves
 * every foreground/background pair the design relies on clears WCAG AA. Raw
 * hex lives here by design - this file is where the approved values are named
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
  "primary-20": "#4A1129",
  "primary-30": "#6F1D45",
  "primary-35": "#7B234D",
  "primary-40": "#8D2A58",
  "primary-45": "#A94A74",
  "primary-60": "#C06E93",
  "primary-70": "#D18FAD",
  "primary-80": "#E0AAC3",
  "primary-90": "#F3C3D6",
  "primary-95": "#FBE4EE",
  "primary-40-rgb": "141 42 88",

  // Layer 2: semantic mappings, resolved through Layer 1.
  "color-bg": "#FFF9FC",
  "color-surface": "#FFFFFF",
  "color-surface-sunken": "#F7F2F4",
  "color-surface-container": "#F1EAED",
  "color-surface-container-high": "#EAE2E6",
  "color-border": "#E5E2E1",
  "color-border-strong": "#7D6E75",
  "color-text": "#1A1A18",
  "color-text-secondary": "#655B60",
  "color-text-tertiary": "#7D6E75",
  "color-text-inverse": "#FFFFFF",
  "color-accent": "#8D2A58",
  "color-accent-hover": "#7B234D",
  "color-accent-active": "#6F1D45",
  "color-accent-subtle": "#F3C3D6",
  "color-accent-container": "#F3C3D6",
  "color-focus-ring": "#8D2A58",
  "color-success": "#176B45",
  "color-success-subtle": "#E7F5EC",
  "color-warning": "#7A4A00",
  "color-warning-subtle": "#FFF3D6",
  "color-danger": "#A61B1B",
  "color-danger-subtle": "#FDECEC",
  "color-info": "#245B78",
  "color-info-subtle": "#E7F1F8",
  "color-bubble-out": "#8D2A58",
  "color-bubble-in": "#F0EDED",
  "color-bubble-agent-in": "#F3C3D6",
  "color-highlight": "#F5A623",
};

describe("Soft Sakura token contract", () => {
  it.each(Object.entries(APPROVED))("--%s is %s", (name, value) => {
    expect(resolve(name)).toBe(value);
  });

  it("gradient-brand keeps both locked stops", () => {
    const gradient = resolve("gradient-brand");
    expect(gradient).toContain("#F3BED3");
    expect(gradient).toContain("#FFF3F8");
  });

  it("gradient-veil keeps the locked bottom stop and fades the top", () => {
    const gradient = resolve("gradient-veil");
    expect(gradient).toContain("#F3BED3");
    expect(gradient).toContain("rgb(255 243 248 / 0)");
  });
});

const AA = 4.5;
const AA_NON_TEXT = 3;

const AA_PAIRS: Array<[string, string]> = [
  ["color-text", "color-bg"],
  ["color-text", "color-surface"],
  ["color-text-secondary", "color-bg"],
  ["color-text-secondary", "color-surface"],
  ["color-text-secondary", "color-surface-sunken"],
  ["color-text-tertiary", "color-surface"],
  ["color-text-tertiary", "color-bg"],
  ["color-text-inverse", "color-accent"],
  ["color-text-inverse", "color-danger"],
  ["color-text-inverse", "color-bubble-out"],
  ["color-accent", "color-accent-subtle"],
  ["color-accent-active", "color-accent-subtle"],
  ["color-accent", "color-accent-container"],
  ["color-text", "color-bubble-agent-in"],
  ["color-text", "color-bubble-in"],
  ["color-text", "color-highlight"],
  ["color-success", "color-success-subtle"],
  ["color-warning", "color-warning-subtle"],
  ["color-danger", "color-danger-subtle"],
  ["color-info", "color-info-subtle"],
];

describe("WCAG AA text pairs", () => {
  it.each(AA_PAIRS)("%s on %s clears AA", (foreground, background) => {
    const ratio = contrastRatio(resolve(foreground), resolve(background));
    expect(
      ratio,
      `${foreground} on ${background} = ${ratio.toFixed(2)}:1`
    ).toBeGreaterThanOrEqual(AA);
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
