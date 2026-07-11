import { headers } from "next/headers";
import { notFound } from "next/navigation";
import { resolveTenantBySlug, SLUG_HEADER } from "@/lib/tenant";

/**
 * T-005: the customer surface's branded shell. Resolves the slug proxy.ts
 * attached to the request, shows the calm not-found state for an unknown
 * slug, and the unavailable state for a suspended tenant. The chat itself
 * (message list, composer, streaming) is built in T-011 inside this shell.
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
      <div className="flex flex-1 items-center justify-center px-8 text-center">
        <p className="max-w-md text-body text-text-secondary">
          Chat with {displayName} is coming soon.
        </p>
      </div>
    </main>
  );
}
