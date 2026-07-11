const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Headers proxy.ts sets so server components can read the resolved surface/slug. */
export const SURFACE_HEADER = "x-wren-surface";
export const SLUG_HEADER = "x-wren-slug";

export type Surface = "platform" | "tenant-admin" | "customer";

export interface HostResolution {
  surface: Surface | null;
  slug: string | null;
}

/**
 * Pure host -> surface/slug mapping (T-005): admin.* -> platform, app.* ->
 * tenant-admin, {slug}.* -> customer. A bare host with no subdomain (e.g. plain
 * "localhost") resolves to neither - the caller decides the fallback.
 */
export function resolveHost(host: string): HostResolution {
  const hostname = host.split(":")[0]?.toLowerCase() ?? "";
  const labels = hostname.split(".").filter(Boolean);
  if (labels.length < 2) return { surface: null, slug: null };

  const [subdomain] = labels;
  if (subdomain === "admin") return { surface: "platform", slug: null };
  if (subdomain === "app") return { surface: "tenant-admin", slug: null };
  return { surface: "customer", slug: subdomain ?? null };
}

export interface TenantResolution {
  id: string;
  name: string;
  status: string;
  brand: Record<string, unknown>;
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
