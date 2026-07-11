import { headers } from "next/headers";
import { notFound } from "next/navigation";
import { resolveTenantBySlug, SLUG_HEADER } from "@/lib/tenant";
import { CustomerChat } from "./CustomerChat";

/**
 * T-005/T-011: the customer surface. Resolves the slug proxy.ts attached to
 * the request (server-side, so brand never flashes to default), shows the
 * calm not-found state for an unknown slug and the unavailable state for a
 * suspended tenant, then hands off to CustomerChat for the actual
 * conversation once the tenant is confirmed active.
 */
export default async function CustomerHome() {
  const slug = (await headers()).get(SLUG_HEADER);
  if (!slug) notFound();

  const tenant = await resolveTenantBySlug(slug);
  if (!tenant) notFound();

  const displayName = (tenant.brand.display_name as string | undefined) ?? tenant.name;
  const logoUrl = tenant.brand.logo_url as string | undefined;

  if (tenant.status === "suspended") {
    return (
      <main className="flex flex-1 flex-col items-center justify-center gap-2 px-8 text-center">
        <h1 className="text-title-2 font-semibold text-text">{displayName}</h1>
        <p className="text-body text-text-secondary">
          This assistant is currently unavailable.
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto flex w-full max-w-[720px] flex-1 flex-col">
      <header className="flex items-center gap-3 border-b border-border px-6 py-4">
        {logoUrl ? (
          // eslint-disable-next-line @next/next/no-img-element -- tenant-supplied, unknown dimensions
          <img src={logoUrl} alt="" className="h-8 w-8 rounded-full object-cover" />
        ) : null}
        <h1 className="text-title-3 font-semibold text-text">{displayName}</h1>
      </header>
      <CustomerChat slug={slug} displayName={displayName} />
    </main>
  );
}
