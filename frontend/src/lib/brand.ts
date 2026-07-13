/**
 * T-032 (docs/design/frontend.md section 5): per-tenant runtime branding.
 *
 * `tenant_config.brand.accent` (validated server-side as #RRGGBB at write
 * time, re-validated here defensively) becomes a scoped CSS override injected
 * by the customer surface's server page - accent, hover/active/subtle steps
 * derived via simple HSL lightness shifts, focus ring following the accent.
 * If the accent fails WCAG AA contrast (4.5:1) against the light surface, the
 * whole override is skipped and the default clay ramp stays.
 *
 * The override is scoped to LIGHT mode only (`prefers-color-scheme: light`
 * plus the explicit `:root[data-theme="light"]` toggle state). Dark mode
 * keeps the default ramp: the derived subtle step is a near-white pastel that
 * pairs with dark-on-light text, and blindly overriding `:root` would win
 * over the media-query dark values and produce light-on-light chat bubbles.
 */

/** Light-mode `--color-surface` from theme.css (layer 2). Kept in one place -
 * if the theme's light surface ever changes, update this constant with it. */
export const SURFACE_LIGHT = "#FFFFFF";

const WCAG_AA_CONTRAST = 4.5;

export type Rgb = [number, number, number];

export function parseHex(hex: string): Rgb | null {
  const match = /^#([0-9a-fA-F]{6})$/.exec(hex.trim());
  if (!match) return null;
  const value = parseInt(match[1] ?? "", 16);
  return [(value >> 16) & 0xff, (value >> 8) & 0xff, value & 0xff];
}

function toHex([r, g, b]: Rgb): string {
  const channel = (n: number) =>
    Math.max(0, Math.min(255, Math.round(n)))
      .toString(16)
      .padStart(2, "0");
  return `#${channel(r)}${channel(g)}${channel(b)}`.toUpperCase();
}

function relativeLuminance([r, g, b]: Rgb): number {
  const linear = (channel: number) => {
    const c = channel / 255;
    return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b);
}

/** WCAG 2.x contrast ratio between two #RRGGBB colors; 0 if either is invalid. */
export function contrastRatio(hexA: string, hexB: string): number {
  const a = parseHex(hexA);
  const b = parseHex(hexB);
  if (!a || !b) return 0;
  const la = relativeLuminance(a);
  const lb = relativeLuminance(b);
  const [lighter, darker] = la >= lb ? [la, lb] : [lb, la];
  return (lighter + 0.05) / (darker + 0.05);
}

function rgbToHsl([r, g, b]: Rgb): [number, number, number] {
  const rn = r / 255;
  const gn = g / 255;
  const bn = b / 255;
  const max = Math.max(rn, gn, bn);
  const min = Math.min(rn, gn, bn);
  const l = (max + min) / 2;
  if (max === min) return [0, 0, l];
  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  let h: number;
  if (max === rn) h = ((gn - bn) / d + (gn < bn ? 6 : 0)) / 6;
  else if (max === gn) h = ((bn - rn) / d + 2) / 6;
  else h = ((rn - gn) / d + 4) / 6;
  return [h, s, l];
}

function hslToRgb([h, s, l]: [number, number, number]): Rgb {
  if (s === 0) {
    const gray = l * 255;
    return [gray, gray, gray];
  }
  const hueToChannel = (p: number, q: number, t: number) => {
    let tn = t;
    if (tn < 0) tn += 1;
    if (tn > 1) tn -= 1;
    if (tn < 1 / 6) return p + (q - p) * 6 * tn;
    if (tn < 1 / 2) return q;
    if (tn < 2 / 3) return p + (q - p) * (2 / 3 - tn) * 6;
    return p;
  };
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
  const p = 2 * l - q;
  return [
    hueToChannel(p, q, h + 1 / 3) * 255,
    hueToChannel(p, q, h) * 255,
    hueToChannel(p, q, h - 1 / 3) * 255,
  ];
}

function shiftLightness(hex: string, delta: number): string {
  const rgb = parseHex(hex);
  if (!rgb) return hex;
  const [h, s, l] = rgbToHsl(rgb);
  return toHex(hslToRgb([h, s, Math.max(0, Math.min(1, l + delta))]));
}

export interface BrandVars {
  accent: string;
  accentHover: string;
  accentActive: string;
  accentSubtle: string;
  focusRing: string;
}

/**
 * Derive the full accent step set from a tenant accent, or null when the
 * accent is missing/invalid/fails AA against the light surface (callers then
 * keep the default clay ramp). Lightness deltas mirror the clay ramp's own
 * spacing (500 -> 600 -> 700, and 100 for the subtle wash).
 */
export function deriveBrandVars(accent: unknown): BrandVars | null {
  if (typeof accent !== "string") return null;
  const rgb = parseHex(accent);
  if (!rgb) return null;
  if (contrastRatio(accent, SURFACE_LIGHT) < WCAG_AA_CONTRAST) return null;
  const normalized = toHex(rgb);
  const [h, s] = rgbToHsl(rgb);
  return {
    accent: normalized,
    accentHover: shiftLightness(normalized, -0.09),
    accentActive: shiftLightness(normalized, -0.18),
    accentSubtle: toHex(hslToRgb([h, Math.min(s, 0.7), 0.94])),
    focusRing: normalized,
  };
}

/**
 * The CSS text the customer surface injects server-side (no flash of default
 * branding), or null when the tenant has no usable accent. Scoped to light
 * mode only - see the module docstring for why dark keeps the default ramp.
 */
export function brandStyle(brand: Record<string, unknown>): string | null {
  const vars = deriveBrandVars(brand["accent"]);
  if (!vars) return null;
  const declarations =
    `--color-accent:${vars.accent};` +
    `--color-accent-hover:${vars.accentHover};` +
    `--color-accent-active:${vars.accentActive};` +
    `--color-accent-subtle:${vars.accentSubtle};` +
    `--color-focus-ring:${vars.focusRing};`;
  return (
    `@media (prefers-color-scheme: light){:root:not([data-theme="dark"]){${declarations}}}` +
    `:root[data-theme="light"]{${declarations}}`
  );
}
