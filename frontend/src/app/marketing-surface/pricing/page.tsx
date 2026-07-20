import type { Metadata } from "next";
import { headers } from "next/headers";
import { surfaceUrl } from "@/lib/tenant";
import { Icon } from "@/components/ui/Icon";

/**
 * /pricing - deliberately honest while Wren is in beta. The prominent banner
 * states the product is free during beta and the tiers are illustrative until
 * launch, which is what keeps this page inside the copy rule (no invented live
 * prices, no fabricated SLAs). Tiers differ only on mechanics that exist in
 * this repo: knowledge documents, conversation volume, escalation seats,
 * dashboards, and subdomain vs a planned custom domain.
 */

export const metadata: Metadata = {
  title: "Pricing - Wren",
  description:
    "Wren is free while in beta. The tiers shown are illustrative placeholders until launch, differentiated only on real mechanics: knowledge documents, conversation volume, escalation seats, dashboards, and custom domains.",
};

interface Tier {
  name: string;
  pitch: string;
  price: string;
  features: string[];
  featured?: boolean;
}

const TIERS: Tier[] = [
  {
    name: "Starter",
    pitch: "A single business getting its first agent live.",
    price: "Free in beta",
    features: [
      "Up to ~50 knowledge documents (illustrative)",
      "Up to ~1,000 conversations / month (illustrative)",
      "1 escalation seat",
      "Cost and eval dashboards",
      "Your own {slug}.wren.app subdomain",
    ],
  },
  {
    name: "Growth",
    pitch: "A busy business handling real customer volume.",
    price: "Free in beta",
    featured: true,
    features: [
      "Up to ~500 knowledge documents (illustrative)",
      "Up to ~10,000 conversations / month (illustrative)",
      "Up to 5 escalation seats",
      "Cost and eval dashboards",
      "Your own {slug}.wren.app subdomain",
    ],
  },
  {
    name: "Scale",
    pitch: "Higher volume and a domain of your own.",
    price: "Free in beta",
    features: [
      "Higher knowledge document ceiling (illustrative)",
      "Higher conversation volume (illustrative)",
      "More escalation seats",
      "Cost and eval dashboards",
      "Custom domain (planned)",
    ],
  },
];

const INCLUDED = [
  "Cited answers grounded in your own documents",
  "Deterministic quotes computed in exact cents",
  "Human handoff from your console",
  "Per-tenant data isolation with row-level security",
];

interface Faq {
  id: string;
  q: string;
  a: string;
}

const FAQS: Faq[] = [
  {
    id: "faq-beta",
    q: "What does free while in beta mean?",
    a: "Right now Wren costs nothing to use. There is no billing wired up during the beta - you onboard, run your agent, and use every feature at no charge.",
  },
  {
    id: "faq-launch",
    q: "What happens when the beta ends?",
    a: "The tiers on this page are illustrative placeholders, not committed prices. Before any paid plan goes live you will be told the real terms in advance, and nothing will start charging automatically without your explicit action.",
  },
  {
    id: "faq-data",
    q: "Can I leave and keep my data?",
    a: "Your knowledge, config, and conversations are yours. Each tenant's data is isolated behind row-level security, and the intent is that you can export and take it with you.",
  },
  {
    id: "faq-price",
    q: "Does the AI ever set a price?",
    a: "Never. The model only selects rules, items, and quantities. A pricing engine computes every total in integer cents, and a validation layer rejects any monetary figure the engine did not produce - enforced at the agent, validation, and API layers.",
  },
  {
    id: "faq-ai",
    q: "Is my data used to train models?",
    a: "No. Your documents are used only to answer your own customers' questions, grounded with citations. They are not used to train shared models.",
  },
];

export default async function PricingPage() {
  const host = (await headers()).get("host") ?? "";
  const businessSignup = surfaceUrl({ surface: "tenant-admin" }, host, "/signup");

  return (
    <>
      {/* Hero */}
      <section className="px-4 sm:px-8">
        <div className="mx-auto flex w-full max-w-[1080px] flex-col items-start gap-6 py-16 sm:items-center sm:py-20 sm:text-center">
          <p className="rounded-full border border-border bg-surface px-3 py-1 text-footnote font-medium text-text-secondary">
            Pricing
          </p>
          <h1 className="max-w-[20ch] text-balance font-display text-display font-bold text-text">
            Simple pricing, still in beta.
          </h1>
          <p className="max-w-[60ch] text-body-lg text-text-secondary">
            We would rather be honest than impressive. Here is exactly where pricing stands today.
          </p>
        </div>
      </section>

      {/* Beta banner */}
      <section className="px-4 sm:px-8">
        <div className="mx-auto w-full max-w-[1080px]">
          <div className="flex items-start gap-3 rounded-lg border border-accent bg-accent-subtle p-5">
            <span aria-hidden="true" className="mt-0.5 text-accent">
              <Icon name="verified_user" size={22} />
            </span>
            <p className="text-body-sm text-text">
              <span className="font-semibold">Wren is free while in beta.</span> The tiers below are
              illustrative placeholders to show the shape of future plans - they are not live prices,
              and the numbers on them are examples, not commitments. Nothing bills you today.
            </p>
          </div>
        </div>
      </section>

      {/* Tier cards */}
      <section aria-labelledby="tiers" className="px-4 sm:px-8">
        <h2 id="tiers" className="sr-only">
          Illustrative plans
        </h2>
        <div className="mx-auto grid w-full max-w-[1080px] gap-4 py-12 md:grid-cols-3">
          {TIERS.map((tier) => (
            <article
              key={tier.name}
              className={`flex flex-col gap-4 rounded-lg bg-surface p-6 shadow-1 ${
                tier.featured ? "border-2 border-accent" : "border border-border"
              }`}
            >
              <div className="flex flex-col gap-1">
                <div className="flex items-center gap-2">
                  <h3 className="text-title-3 font-semibold text-text">{tier.name}</h3>
                  {tier.featured ? (
                    <span className="rounded-full bg-accent-container px-2 py-0.5 text-caption font-semibold uppercase text-text-inverse">
                      Beta default
                    </span>
                  ) : null}
                </div>
                <p className="text-body-sm text-text-secondary">{tier.pitch}</p>
              </div>
              <p className="font-display text-title-2 font-semibold text-text">{tier.price}</p>
              <ul className="flex flex-1 flex-col gap-2.5">
                {tier.features.map((f) => (
                  <li key={f} className="flex items-start gap-2 text-body-sm text-text-secondary">
                    <span aria-hidden="true" className="mt-0.5 text-accent">
                      <Icon name="check_circle" size={17} />
                    </span>
                    {f}
                  </li>
                ))}
              </ul>
              <a
                href={businessSignup}
                className={`inline-flex items-center justify-center rounded-md px-4 py-2 text-body-sm font-medium transition-colors duration-fast ${
                  tier.featured
                    ? "border border-transparent bg-accent text-text-inverse hover:bg-accent-hover active:bg-accent-active"
                    : "border border-border bg-surface text-text hover:bg-surface-sunken"
                }`}
              >
                Start free in beta
              </a>
            </article>
          ))}
        </div>
      </section>

      {/* Every plan includes */}
      <section
        aria-labelledby="included"
        className="border-y border-border bg-surface-sunken px-4 sm:px-8"
      >
        <div className="mx-auto w-full max-w-[1080px] py-14">
          <h2 id="included" className="mb-6 font-display text-title-2 font-semibold text-text">
            Every plan includes
          </h2>
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {INCLUDED.map((line) => (
              <li
                key={line}
                className="flex items-start gap-3 rounded-lg border border-border bg-surface p-4 text-body-sm text-text shadow-1"
              >
                <span aria-hidden="true" className="mt-0.5 text-accent">
                  <Icon name="check_circle" size={18} />
                </span>
                {line}
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* FAQ */}
      <section aria-labelledby="faq" className="px-4 sm:px-8">
        <div className="mx-auto w-full max-w-[760px] py-16 sm:py-20">
          <h2 id="faq" className="mb-6 font-display text-title-2 font-semibold text-text">
            Questions worth asking
          </h2>
          <div className="flex flex-col gap-3">
            {FAQS.map((faq) => (
              <details
                key={faq.id}
                id={faq.id}
                className="group rounded-lg border border-border bg-surface p-4 shadow-1"
              >
                <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-body font-medium text-text [&::-webkit-details-marker]:hidden">
                  {faq.q}
                  <span
                    aria-hidden="true"
                    className="text-text-tertiary transition-transform duration-fast group-open:rotate-90"
                  >
                    <Icon name="arrow_forward" size={18} />
                  </span>
                </summary>
                <p className="mt-3 text-body-sm text-text-secondary">{faq.a}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="border-t border-border px-4 sm:px-8">
        <div className="mx-auto flex w-full max-w-[1080px] flex-col items-start gap-4 py-16 sm:items-center sm:py-20 sm:text-center">
          <h2 className="font-display text-title-1 font-semibold text-text">
            Free today, honest tomorrow.
          </h2>
          <p className="max-w-[52ch] text-body text-text-secondary">
            Onboard your business now while the beta is free. No card, no billing.
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
