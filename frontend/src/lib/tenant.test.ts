import { describe, expect, it } from "vitest";
import { resolveHost, surfaceUrl } from "./tenant";

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

  it("maps the bare base host to the marketing surface", () => {
    expect(resolveHost("localhost:3000")).toEqual({ surface: "marketing", slug: null });
    expect(resolveHost("localhost")).toEqual({ surface: "marketing", slug: null });
    expect(resolveHost("wren.app")).toEqual({ surface: "marketing", slug: null });
  });

  it("maps www to the marketing surface, never to a customer slug", () => {
    expect(resolveHost("www.wren.app")).toEqual({ surface: "marketing", slug: null });
    expect(resolveHost("www.localhost:3000")).toEqual({ surface: "marketing", slug: null });
  });

  it("returns no surface/slug for an empty host", () => {
    expect(resolveHost("")).toEqual({ surface: null, slug: null });
  });
});

describe("surfaceUrl", () => {
  it("builds tenant-admin and platform urls preserving host and port", () => {
    expect(surfaceUrl({ surface: "tenant-admin" }, "localhost:3000", "/signup")).toBe(
      "http://app.localhost:3000/signup",
    );
    expect(surfaceUrl({ surface: "platform" }, "localhost:3000", "/login")).toBe(
      "http://admin.localhost:3000/login",
    );
  });

  it("builds customer urls from a slug, defaulting to the root path", () => {
    expect(surfaceUrl({ surface: "customer", slug: "bytefix" }, "localhost:3000")).toBe(
      "http://bytefix.localhost:3000/",
    );
    expect(surfaceUrl({ surface: "customer", slug: "bytefix" }, "wren.app")).toBe(
      "https://bytefix.wren.app/",
    );
  });

  it("uses https for any non-localhost host", () => {
    expect(surfaceUrl({ surface: "platform" }, "wren.app", "/login")).toBe(
      "https://admin.wren.app/login",
    );
  });

  it("strips a www prefix before prepending the surface subdomain", () => {
    expect(surfaceUrl({ surface: "tenant-admin" }, "www.wren.app", "/login")).toBe(
      "https://app.wren.app/login",
    );
  });

  it("replaces an existing surface subdomain instead of stacking on it", () => {
    expect(surfaceUrl({ surface: "customer", slug: "bytefix" }, "app.localhost:3000")).toBe(
      "http://bytefix.localhost:3000/",
    );
    expect(surfaceUrl({ surface: "tenant-admin" }, "bytefix.wren.app", "/login")).toBe(
      "https://app.wren.app/login",
    );
  });
});
