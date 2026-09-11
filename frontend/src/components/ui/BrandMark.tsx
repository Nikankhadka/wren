/**
 * Tenant brand mark: the tenant's logo when set, otherwise a monogram avatar
 * (first letter of the display name on the brand gradient in the accent
 * color). Used by the customer chat header and the tenant-admin console
 * sidebar. The gradient is fixed - the tenant's stored accent is no longer
 * injected (D25); the berry initial on the pale end passes AA on its own.
 */
export function BrandMark({ logoUrl, name }: { logoUrl?: string | null; name: string }) {
  if (logoUrl) {
    return (
      // eslint-disable-next-line @next/next/no-img-element -- tenant-supplied, unknown dimensions
      <img src={logoUrl} alt="" className="h-8 w-8 rounded-full object-cover" />
    );
  }
  const initial = name.trim().charAt(0).toUpperCase() || "?";
  return (
    <span
      aria-hidden
      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand text-body-sm font-semibold text-accent"
    >
      {initial}
    </span>
  );
}