#!/usr/bin/env node
/*
 * Token guard (docs/design/frontend.md section 1, rule 2):
 * raw color literals (hex / rgb() / hsl() / oklch()) are allowed ONLY in
 * src/styles/theme.css. Anything else under src/ fails the build.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const ROOT = new URL("..", import.meta.url).pathname;
const SRC = join(ROOT, "src");
const ALLOWED = new Set(["src/styles/theme.css"]);
const EXTENSIONS = new Set([".ts", ".tsx", ".js", ".jsx", ".css", ".mjs"]);

const COLOR_LITERAL =
  /(#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?|oklch|oklab)\s*\()/g;

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) walk(path, out);
    else if (EXTENSIONS.has(name.slice(name.lastIndexOf(".")))) out.push(path);
  }
  return out;
}

const violations = [];
for (const file of walk(SRC)) {
  const rel = relative(ROOT, file);
  if (ALLOWED.has(rel)) continue;
  const lines = readFileSync(file, "utf8").split("\n");
  lines.forEach((line, i) => {
    const matches = line.match(COLOR_LITERAL);
    if (matches) violations.push(`${rel}:${i + 1}  ${line.trim()}`);
  });
}

if (violations.length > 0) {
  console.error("Color literals outside src/styles/theme.css (use semantic tokens - see docs/design/frontend.md):\n");
  for (const v of violations) console.error("  " + v);
  process.exit(1);
}
console.log("check-tokens: OK (no raw color values outside theme.css)");
