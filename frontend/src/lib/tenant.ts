const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Headers proxy.ts sets so server components can read the resolved surface/slug. */
export const SURFACE_HEADER = "x-wren-surface";
export const SLUG_HEADER = "x-wren-slug";

export type Surface = "platform" | "tenant-admin" | "customer" | "marketing";

export interface HostResolution {
  surface: Surface | null;
  slug: string | null;
}

/**
 * The apex hosts whose bare (or www.) form is the public marketing surface.
 * "wren.app" mirrors the backend's CORS origin regex (app/main.py) - the one
 * other place the production base domain is already named.
 */
const BASE_HOSTS = ["localhost", "wren.app"];

/**
 * Pure host -> surface/slug mapping (T-005): admin.* -> platform, app.* ->
 * tenant-admin, {slug}.* -> customer, and the bare base host (or www.) ->
 * marketing. An empty host resolves to neither - the caller decides the
 * fallback.
 */
export function resolveHost(host: string): HostResolution {
  const hostname = host.split(":")[0]?.toLowerCase() ?? "";
  const bare = hostname.startsWith("www.") ? hostname.slice(4) : hostname;
  if (BASE_HOSTS.includes(bare)) return { surface: "marketing", slug: null };

  const labels = hostname.split(".").filter(Boolean);
  if (labels.length < 2) return { surface: null, slug: null };

  const [subdomain] = labels;
  if (subdomain === "admin") return { surface: "platform", slug: null };
  if (subdomain === "app") return { surface: "tenant-admin", slug: null };
  return { surface: "customer", slug: subdomain ?? null };
}

export type SurfaceTarget =
  | { surface: "platform" | "tenant-admin" }
  | { surface: "customer"; slug: string };

/**
 * Inverse of resolveHost: an absolute URL for another surface, derived from
 * the current request host so the base domain and port carry over unchanged
 * (app.localhost:3000 in dev, app.wren.app in prod - never hardcoded). Any
 * surface subdomain (or www.) on the current host is stripped before the
 * target's is prepended. Plain http only for localhost.
 */
export function surfaceUrl(target: SurfaceTarget, currentHost: string, path = "/"): string {
  const [hostname = "", port] = currentHost.toLowerCase().split(":");
  const { surface } = resolveHost(hostname);
  const base =
    surface === "marketing" || surface === null
      ? hostname.startsWith("www.")
        ? hostname.slice(4)
        : hostname
      : hostname.split(".").slice(1).join(".");

  const subdomain =
    target.surface === "customer" ? target.slug : target.surface === "platform" ? "admin" : "app";
  const protocol = base === "localhost" || base.endsWith(".localhost") ? "http" : "https";
  return `${protocol}://${subdomain}.${base}${port ? `:${port}` : ""}${path}`;
}

export interface TenantResolution {
  id: string;
  name: string;
  status: string;
  brand: Record<string, unknown>;
  /** T-032: tenant-configured customer-surface block (config->'customer'):
   * optional greeting + starter_questions. Empty object when unconfigured,
   * absent entirely if a pre-T-032 backend answered this request. */
  customer?: Record<string, unknown>;
}

/**
 * Typed view over TenantResolution.customer with safe fallbacks. Accepts
 * undefined so a frontend deployed ahead of a pre-T-032 backend (missing the
 * `customer` field entirely) degrades to the no-greeting/no-chips state
 * instead of throwing - deploy order between the two should never matter.
 */
export function customerSurfaceConfig(customer: Record<string, unknown> | undefined): {
  greeting: string | null;
  starterQuestions: string[];
} {
  customer ??= {};
  const greeting =
    typeof customer["greeting"] === "string" && customer["greeting"].trim() !== ""
      ? customer["greeting"]
      : null;
  const raw = customer["starter_questions"];
  const starterQuestions = Array.isArray(raw)
    ? raw.filter((q): q is string => typeof q === "string" && q.trim() !== "").slice(0, 3)
    : [];
  return { greeting, starterQuestions };
}

/**
 * Server-side, unauthenticated fetch of GET /api/public/tenant/{slug} (T-005).
 * Returns null for an unknown slug (404) so callers can render the calm
 * not-found state instead of throwing.
 */
export async function resolveTenantBySlug(slug: string): Promise<TenantResolution | null> {
  const res = await fetch(`${API_URL}/api/public/tenant/${encodeURIComponent(slug)}`, {
    cache: "no-store",
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`tenant resolve failed: ${res.status}`);
  return (await res.json()) as TenantResolution;
}
