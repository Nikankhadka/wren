import { describe, expect, it } from "vitest";
import { isTabActive, navTone, type TabItem } from "./TabBar";

function item(overrides: Partial<TabItem> = {}): TabItem {
  return { href: "/home", label: "Home", icon: "home", ...overrides };
}

describe("navTone", () => {
  it("renders the accent wash for the active tab on every surface", () => {
    expect(navTone(true, "text-text-secondary")).toBe("bg-accent-a09 text-accent-active");
    expect(navTone(true, "text-ink-a40")).toBe("bg-accent-a09 text-accent-active");
  });

  it("keeps the surface's muted text with an accent hover when inactive", () => {
    expect(navTone(false, "text-text-secondary")).toBe(
      "text-text-secondary hover:bg-accent-a07 hover:text-accent-active",
    );
    expect(navTone(false, "text-ink-a40")).toBe(
      "text-ink-a40 hover:bg-accent-a07 hover:text-accent-active",
    );
  });
});

describe("isTabActive", () => {
  it("matches the tab's own path and anything under it", () => {
    expect(isTabActive(item({ href: "/business" }), "/business")).toBe(true);
    expect(isTabActive(item({ href: "/business" }), "/business/offerings")).toBe(true);
    expect(isTabActive(item({ href: "/business" }), "/home")).toBe(false);
  });

  it("honours the owns prefixes for destinations outside the tab's URL", () => {
    const business = item({ href: "/business", owns: ["/settings"] });
    expect(isTabActive(business, "/settings")).toBe(true);
    expect(isTabActive(business, "/home")).toBe(false);
  });
});
