import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { resolveHost, SLUG_HEADER, SURFACE_HEADER } from "@/lib/tenant";

/**
 * T-005: host -> surface routing. Named `proxy.ts` per Next.js 16 (the
 * `middleware.ts` convention is deprecated - see
 * node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions/proxy.md).
 *
 * `X-Wren-Slug` lets tests force the customer surface without a real subdomain
 * (ticket T-005). Tenant-admin still has no root page (console pages live at
 * `/conversations` etc, login/signup at their own paths) - without this
 * guard, its `/` would silently fall through to the customer surface's
 * `(customer)/page.tsx`, which also resolves to `/` (route groups do not
 * segment URLs).
 *
 * Platform (T-033) DOES need a root page and its own `/login` - both of
 * which the customer and tenant-admin surfaces already occupy. Route groups
 * can't solve this (they don't segment URLs, Next's file router only sees
 * literal pathnames - `(platform)/page.tsx` and `(customer)/page.tsx` both
 * resolve to `/` and fail the build outright as a routing collision). So
 * platform's pages live under the real top-level segment `admin-surface/`
 * instead, and every platform-surface request gets internally rewritten from
 * its public path (e.g. `admin.wren.app/login`) to `/admin-surface/login` -
 * invisible to the browser (the URL bar is untouched), resolved only by
 * Next's router. `Link href`s inside admin-surface pages stay as the public
 * path ("/login", never "/admin-surface/login").
 *
 * The marketing surface (bare apex / www, resolved by resolveHost) uses the
 * same rewrite pattern into `marketing-surface/` - the landing page's public
 * URL is `/` but that pathname is owned by `(customer)/page.tsx`.
 */
export function proxy(request: NextRequest): NextResponse {
  const slugOverride = request.headers.get(SLUG_HEADER);
  const { surface, slug } = slugOverride
    ? { surface: "customer" as const, slug: slugOverride }
    : resolveHost(request.headers.get("host") ?? "");

  if (surface === "tenant-admin" && request.nextUrl.pathname === "/") {
    return new NextResponse(null, { status: 404 });
  }

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set(SURFACE_HEADER, surface ?? "");
  requestHeaders.set(SLUG_HEADER, slug ?? "");

  if (surface === "platform") {
    const url = request.nextUrl.clone();
    url.pathname = `/admin-surface${url.pathname}`;
    return NextResponse.rewrite(url, { request: { headers: requestHeaders } });
  }

  if (surface === "marketing") {
    const url = request.nextUrl.clone();
    url.pathname = `/marketing-surface${url.pathname}`;
    return NextResponse.rewrite(url, { request: { headers: requestHeaders } });
  }

  return NextResponse.next({ request: { headers: requestHeaders } });
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
