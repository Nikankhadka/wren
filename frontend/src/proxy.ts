import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { resolveHost, SLUG_HEADER, SURFACE_HEADER } from "@/lib/tenant";

/**
 * T-005: host -> surface routing. Named `proxy.ts` per Next.js 16 (the
 * `middleware.ts` convention is deprecated - see
 * node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions/proxy.md).
 *
 * `X-Wren-Slug` lets tests force the customer surface without a real subdomain
 * (ticket T-005). Platform/tenant-admin have no root page yet - without this
 * guard, their `/` would silently fall through to the customer surface's
 * `(customer)/page.tsx`, which also resolves to `/` (route groups do not
 * segment URLs). Replace this guard with real routing once those surfaces get
 * their own root pages, don't just delete it.
 */
export function proxy(request: NextRequest): NextResponse {
  const slugOverride = request.headers.get(SLUG_HEADER);
  const { surface, slug } = slugOverride
    ? { surface: "customer" as const, slug: slugOverride }
    : resolveHost(request.headers.get("host") ?? "");

  if ((surface === "platform" || surface === "tenant-admin") && request.nextUrl.pathname === "/") {
    return new NextResponse(null, { status: 404 });
  }

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set(SURFACE_HEADER, surface ?? "");
  requestHeaders.set(SLUG_HEADER, slug ?? "");
  return NextResponse.next({ request: { headers: requestHeaders } });
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
