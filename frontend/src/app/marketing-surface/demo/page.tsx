import type { Metadata } from "next";
import { headers } from "next/headers";
import { surfaceUrl } from "@/lib/tenant";
import { Icon } from "@/components/ui/Icon";
import type { IconName } from "@/components/ui/Icon";

/**
 * /demo - the guided tour, always on. The credentials here are intentionally
 * public demo identities from the seeded demo world (scripts/demo.sh /
 * seed_demo.py), not secrets. Steps mirror docs/DEMO.md exactly so the two
 * never disagree; every referenced screen is a real console page. No env flag
 * gates this page.
 */

/** Persistently seeded demo tenant (T-010 / seed_demo.py) - the live demo link. */
const DEMO_SLUG = "bytefix";
const DEMO_PASSWORD = "wren-demo";

export const metadata: Metadata = {
  title: "Demo - Wren",
  description:
    "See Wren working in about ten minutes with a seeded demo world: chat as a customer, run the business console, and operate the platform. Public demo credentials, no setup.",
};

interface Persona {
  icon: IconName;
  title: string;
  who: string;
  steps: string[];
  cta: { href: string; label: string };
  note?: string;
}

export default async function DemoPage() {
  const host = (await headers()).get("host") ?? "";
  const businessSignup = surfaceUrl({ surface: "tenant-admin" }, host, "/signup");
  const businessLogin = surfaceUrl({ surface: "tenant-admin" }, host, "/login");
  const platformLogin = surfaceUrl({ surface: "platform" }, host, "/login");
  const demoChat = surfaceUrl({ surface: "customer", slug: DEMO_SLUG }, host);

  const personas: Persona[] = [
    {
      icon: "forum",
      title: "Customer",
      who: "No login needed - chat at the demo shop's own address.",
      steps: [
        "Ask a repair question and read the grounded answer with citations",
        "Ask for a quote and watch a deterministic quote card appear",
        "Ask to speak to a human and see the escalation banner take over",
      ],
      cta: { href: demoChat, label: "Open the Bytefix chat" },
    },
    {
      icon: "dashboard",
      title: "Business owner",
      who: "Sign in to the tenant console with a seeded owner.",
      steps: [
        "Open a conversation and read its per-message trace",
        "Claim an open escalation, reply, and resolve it",
        "View pricing rules (dollars in, exact cents stored)",
        "Open the Dashboards page for real cost and eval status",
      ],
      cta: { href: businessLogin, label: "Sign in to the console" },
      note: "owner@bytefix.dev or owner@lumident.dev",
    },
    {
      icon: "verified_user",
      title: "Platform operator",
      who: "Sign in to the admin console as the founder identity.",
      steps: [
        "View the platform metrics across both tenants",
        "Provision a new tenant live from the modal",
        "Suspend a tenant, then reactivate it",
      ],
      cta: { href: platformLogin, label: "Sign in to the admin console" },
      note: "founder@wren.dev",
    },
  ];

  const credentials = [
    { surface: "Customer chat (Bytefix)", email: "none - no login", password: "-" },
    { surface: "Tenant console (Bytefix)", email: "owner@bytefix.dev", password: DEMO_PASSWORD },
    { surface: "Tenant console (Lumident)", email: "owner@lumident.dev", password: DEMO_PASSWORD },
    { surface: "Platform admin", email: "founder@wren.dev", password: DEMO_PASSWORD },
  ];

  return (
    <>
      {/* Hero */}
      <section className="px-4 sm:px-8">
        <div className="mx-auto flex w-full max-w-[1080px] flex-col items-start gap-6 py-16 sm:items-center sm:py-20 sm:text-center">
          <p className="rounded-full border border-border bg-surface px-3 py-1 text-footnote font-medium text-text-secondary">
            Demo
          </p>
          <h1 className="max-w-[22ch] text-balance font-display text-display font-bold text-text">
            See it working in ten minutes.
          </h1>
          <p className="max-w-[62ch] text-body-lg text-text-secondary">
            Pick a role and follow the steps. Everything runs against a seeded demo world with two
            tenants - a phone-repair shop and a dental practice - so you can try every surface without
            setting anything up.
          </p>
          <p className="max-w-[62ch] text-footnote text-text-tertiary">
            The demo world is created by <span className="font-mono">./scripts/demo.sh</span>. On a
            deployment where it has not been seeded, some deep links may land on a calm login or
            not-found page instead - that is expected, not a bug.
          </p>
        </div>
      </section>

      {/* Persona picker */}
      <section aria-labelledby="personas" className="px-4 sm:px-8">
        <div className="mx-auto w-full max-w-[1080px] pb-8">
          <h2 id="personas" className="sr-only">
            Choose a role
          </h2>
          <div className="grid gap-4 md:grid-cols-3">
            {personas.map((persona) => (
              <div
                key={persona.title}
                className="flex flex-col gap-4 rounded-lg border border-border bg-surface p-6 shadow-1"
              >
                <span
                  aria-hidden="true"
                  className="flex h-10 w-10 items-center justify-center rounded-md bg-accent-subtle text-accent"
                >
                  <Icon name={persona.icon} size={22} />
                </span>
                <div className="flex flex-col gap-1">
                  <h3 className="text-title-3 font-semibold text-text">{persona.title}</h3>
                  <p className="text-body-sm text-text-secondary">{persona.who}</p>
                </div>
                <ol className="flex flex-1 flex-col gap-2.5">
                  {persona.steps.map((step, i) => (
                    <li key={step} className="flex items-start gap-2.5 text-body-sm text-text">
                      <span
                        aria-hidden="true"
                        className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent-container text-caption font-semibold text-text-inverse"
                      >
                        {i + 1}
                      </span>
                      {step}
                    </li>
                  ))}
                </ol>
                {persona.note ? (
                  <p className="text-footnote text-text-tertiary">
                    Use <span className="font-mono text-text-secondary">{persona.note}</span> with
                    password <span className="font-mono text-text-secondary">{DEMO_PASSWORD}</span>.
                  </p>
                ) : null}
                <a
                  href={persona.cta.href}
                  className="inline-flex items-center justify-center gap-1.5 rounded-md border border-border bg-surface px-4 py-2 text-body-sm font-medium text-text transition-colors duration-fast hover:bg-surface-sunken"
                >
                  {persona.cta.label}
                  <Icon name="arrow_forward" size={16} />
                </a>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Credentials table */}
      <section
        aria-labelledby="credentials"
        className="border-y border-border bg-surface-sunken px-4 sm:px-8"
      >
        <div className="mx-auto w-full max-w-[1080px] py-14">
          <h2 id="credentials" className="mb-2 font-display text-title-2 font-semibold text-text">
            Demo credentials
          </h2>
          <p className="mb-6 text-body-sm text-text-secondary">
            These are public demo identities, seeded on purpose. The password is the same for every
            login.
          </p>
          <div className="overflow-x-auto rounded-lg border border-border bg-surface">
            <table className="w-full text-body-sm">
              <thead className="bg-surface-sunken">
                <tr>
                  <th className="px-4 py-2 text-left font-medium text-text-secondary">Surface</th>
                  <th className="px-4 py-2 text-left font-medium text-text-secondary">Email</th>
                  <th className="px-4 py-2 text-left font-medium text-text-secondary">Password</th>
                </tr>
              </thead>
              <tbody>
                {credentials.map((row) => (
                  <tr key={row.surface} className="border-t border-border">
                    <td className="px-4 py-3 text-text">{row.surface}</td>
                    <td className="px-4 py-3 font-mono text-text">{row.email}</td>
                    <td className="px-4 py-3 font-mono text-text">{row.password}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* Why two tenants */}
      <section aria-labelledby="two-tenants" className="px-4 sm:px-8">
        <div className="mx-auto w-full max-w-[1080px] py-16 sm:py-20">
          <h2 id="two-tenants" className="mb-2 font-display text-title-2 font-semibold text-text">
            Why there are two tenants
          </h2>
          <p className="max-w-[68ch] text-body text-text-secondary">
            Bytefix is a phone-repair shop; Lumident is a dental practice. They exist together on
            purpose. Wren is domain-agnostic by construction - no code branches on a business
            vertical anywhere. The two tenants run the exact same code, and everything that makes
            them feel different (services, prices, policies, knowledge) lives entirely in tenant
            config and uploaded documents. Onboarding a second, unrelated business by config alone
            is the proof.
          </p>
        </div>
      </section>

      {/* CTA */}
      <section className="border-t border-border px-4 sm:px-8">
        <div className="mx-auto flex w-full max-w-[1080px] flex-col items-start gap-4 py-16 sm:items-center sm:py-20 sm:text-center">
          <h2 className="font-display text-title-1 font-semibold text-text">
            Ready to run your own?
          </h2>
          <p className="max-w-[52ch] text-body text-text-secondary">
            The demo shows the shape. Onboard your real business the same way.
          </p>
          <a
            href={businessSignup}
            className="inline-flex items-center justify-center rounded-md border border-transparent bg-accent px-5 py-2.5 text-body font-medium text-text-inverse transition-colors duration-fast hover:bg-accent-hover active:bg-accent-active"
          >
            Create your agent
          </a>
        </div>
      </section>
    </>
  );
}
