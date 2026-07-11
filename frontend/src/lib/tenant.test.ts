import { describe, expect, it } from "vitest";
import { resolveHost } from "./tenant";

describe("resolveHost", () => {
  it("maps the admin subdomain to the platform surface", () => {
    expect(resolveHost("admin.wren.app")).toEqual({ surface: "platform", slug: null });
    expect(resolveHost("admin.localhost:3000")).toEqual({ surface: "platform", slug: null });
  });

  it("maps the app subdomain to the tenant-admin surface", () => {
    expect(resolveHost("app.wren.app")).toEqual({ surface: "tenant-admin", slug: null });
    expect(resolveHost("app.localhost:3000")).toEqual({ surface: "tenant-admin", slug: null });
  });

  it("maps any other subdomain to the customer surface with that slug", () => {
    expect(resolveHost("bytefix.wren.app")).toEqual({ surface: "customer", slug: "bytefix" });
    expect(resolveHost("bytefix.localhost:3000")).toEqual({ surface: "customer", slug: "bytefix" });
  });

  it("is case-insensitive on the hostname", () => {
    expect(resolveHost("ByteFix.Wren.App")).toEqual({ surface: "customer", slug: "bytefix" });
  });

  it("returns no surface/slug for a bare host with no subdomain", () => {
    expect(resolveHost("localhost:3000")).toEqual({ surface: null, slug: null });
    expect(resolveHost("localhost")).toEqual({ surface: null, slug: null });
  });
});
