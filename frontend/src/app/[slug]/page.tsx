import { notFound } from "next/navigation";
import {
  customerSurfaceConfig,
  resolveStorefrontBySlug,
  resolveTenantBySlug,
} from "@/lib/tenant";
import { BrandMark } from "@/components/ui/BrandMark";
import { CustomerChat } from "./CustomerChat";
import { Storefront } from "./Storefront";

/**
 * T-005/T-011/T-032: the customer surface, at `/{slug}` (D22 - the slug is a
 * path segment, not a subdomain). Resolves the tenant server-side so its name
 * and logo never flash to default (the stored accent is visually retired -
 * D25), shows the calm not-found state for an unknown slug and the
 * unavailable state for a suspended tenant, then hands off to CustomerChat
 * with the tenant-configured greeting + starter chips.
 *
 * This is the app's only dynamic top-level segment, so it catches every path
 * the console's static routes do not. Next resolves static segments before
 * dynamic ones, which is what keeps `/settings` the console and `/bytefix` a
 * tenant; `RESERVED_SLUGS` (backend/app/features/tenants/api.py) is the other
 * half of that contract - it stops a tenant ever claiming a console name.
 */
export default async function CustomerHome({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const tenant = await resolveTenantBySlug(slug);
  if (!tenant) notFound();

  const storefront = tenant.status === "active" ? await resolveStorefrontBySlug(slug) : null;
  const displayName = storefront?.name ?? (tenant.brand.display_name as string | undefined) ?? tenant.name;
  const logoUrl = tenant.brand.logo_url as string | undefined;
  const { greeting, starterQuestions } = customerSurfaceConfig(tenant.customer);

  if (tenant.status === "suspended") {
    return (
      <main className="flex flex-1 flex-col items-center justify-center gap-2 px-4 text-center sm:px-8">
        <h1 className="text-title-2 font-semibold text-text">{displayName}</h1>
        <p className="text-body text-text-secondary">
          This page is currently unavailable.
        </p>
      </main>
    );
  }

  // A tenant that is neither active nor suspended (`provisioning`, which a
  // platform-created tenant sits at until it is claimed) has no storefront to
  // read, but it does have a working assistant. Fall back to the bare chat
  // rather than rendering an empty page.
  if (!storefront) {
    return (
      <main className="mx-auto flex h-dvh w-full max-w-[720px] flex-col">
        <header className="flex items-center gap-3 border-b border-border px-4 py-4 sm:px-6">
          <BrandMark logoUrl={logoUrl} name={displayName} />
          <h1 className="text-title-3 font-semibold text-text">{displayName}</h1>
        </header>
        <CustomerChat
          slug={slug}
          displayName={displayName}
          greeting={greeting}
          starterQuestions={starterQuestions}
        />
      </main>
    );
  }

  return (
    <>
      <Storefront
        slug={slug}
        logoUrl={logoUrl}
        greeting={greeting}
        starterQuestions={starterQuestions}
        storefront={storefront}
      />
    </>
  );
}
