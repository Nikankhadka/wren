import type { Metadata } from "next";
import { headers } from "next/headers";
import { surfaceUrl } from "@/lib/tenant";
import { Icon } from "@/components/ui/Icon";
import type { IconName } from "@/components/ui/Icon";

/**
 * /about - the trust page. Every claim maps to a real mechanic in this repo
 * (FORCE RLS + dedicated app role, deterministic pricing across three layers,
 * the escalation model, CI-gated eval suites). No fabricated pass-rates or
 * SLAs - screening and leakage are described as measured and gated in CI, not
 * quoted as a number that could not be verified from this page.
 */

export const metadata: Metadata = {
  title: "About - Wren",
  description:
    "Wren is built to be trusted: per-tenant row-level security, deterministic pricing in integer cents, a real human-escalation model, and eval suites gated in CI.",
};

interface Band {
  icon: IconName;
  title: string;
  intro: string;
  points: string[];
}

const BANDS: Band[] = [
  {
    icon: "lock",
    title: "Isolation, by default",
    intro:
      "Every tenant's data is fenced off at the database, not just in application code.",
    points: [
      "Per-tenant Postgres row-level security, with FORCE RLS on and a dedicated application role that has no way around it.",
      "Cross-tenant leakage is held to zero by a leakage test suite gated in CI - one tenant can never read another's rows.",
      "Sessions are JWT-verified; the backend checks every token before it touches tenant data.",
      "Prompt-injection screening runs on inputs and is measured and gated in CI rather than assumed.",
    ],
  },
  {
    icon: "sell",
    title: "Deterministic pricing",
    intro:
      "No language model ever produces a monetary amount. Pricing is computed, in three layers.",
    points: [
      "The agent only selects rules, items, and quantities - never a total.",
      "A pricing engine computes every amount in integer cents, so there is no floating-point drift and no guesswork.",
      "The validation and API layers reject any monetary figure the engine did not compute - the rule is enforced, not merely intended.",
    ],
  },
  {
    icon: "support_agent",
    title: "Humans stay in the loop",
    intro: "The agent knows when to stop and hand a conversation to a person.",
    points: [
      "Low confidence, detected frustration, or an explicit request for a human all trigger an escalation.",
      "The moment a conversation escalates, the AI stops replying - it does not keep talking over a handoff.",
      "Your team claims, replies to, and resolves escalations from the console, and the customer sees the human's reply land in the same chat.",
    ],
  },
];

export default async function AboutPage() {
  const host = (await headers()).get("host") ?? "";
  const businessSignup = surfaceUrl({ surface: "tenant-admin" }, host, "/signup");

  return (
    <>
      {/* Hero */}
      <section className="px-4 sm:px-8">
        <div className="mx-auto flex w-full max-w-[1080px] flex-col items-start gap-6 py-16 sm:items-center sm:py-20 sm:text-center">
          <p className="rounded-full border border-border bg-surface px-3 py-1 text-footnote font-medium text-text-secondary">
            About
          </p>
          <h1 className="max-w-[20ch] text-balance font-display text-display font-bold text-text">
            Built to be trusted.
          </h1>
          <p className="max-w-[64ch] text-body-lg text-text-secondary">
            Wren gives any small business its own private, branded AI agent. The hard part is not
            answering questions - it is answering only from the right knowledge, never inventing a
            price, keeping each business&apos;s data to itself, and knowing when to bring in a human.
            That is what the product is actually built around.
          </p>
        </div>
      </section>

      {/* Trust bands */}
      {BANDS.map((band, index) => (
        <section
          key={band.title}
          aria-labelledby={`band-${index}`}
          className={
            index % 2 === 0
              ? "border-y border-border bg-surface-sunken px-4 sm:px-8"
              : "px-4 sm:px-8"
          }
        >
          <div className="mx-auto grid w-full max-w-[1080px] items-start gap-8 py-16 sm:py-20 md:grid-cols-[1fr_1.4fr]">
            <div className="flex flex-col gap-4">
              <span
                aria-hidden="true"
                className="flex h-11 w-11 items-center justify-center rounded-md bg-accent-subtle text-accent"
              >
                <Icon name={band.icon} size={24} />
              </span>
              <h2
                id={`band-${index}`}
                className="font-display text-title-2 font-semibold text-text"
              >
                {band.title}
              </h2>
              <p className="text-body text-text-secondary">{band.intro}</p>
            </div>
            <ul className="flex flex-col gap-3">
              {band.points.map((point) => (
                <li
                  key={point}
                  className="flex items-start gap-3 rounded-lg border border-border bg-surface p-4 text-body-sm text-text shadow-1"
                >
                  <span aria-hidden="true" className="mt-0.5 text-accent">
                    <Icon name="check_circle" size={18} />
                  </span>
                  {point}
                </li>
              ))}
            </ul>
          </div>
        </section>
      ))}

      {/* How we hold ourselves to it */}
      <section
        aria-labelledby="standards"
        className="border-y border-border bg-surface-sunken px-4 sm:px-8"
      >
        <div className="mx-auto w-full max-w-[1080px] py-16 sm:py-20">
          <h2 id="standards" className="mb-2 font-display text-title-2 font-semibold text-text">
            How we hold ourselves to it
          </h2>
          <p className="mb-6 max-w-[64ch] text-body text-text-secondary">
            Claims are cheap. These are held to standards that run automatically.
          </p>
          <div className="grid gap-6 sm:grid-cols-2">
            <article className="flex flex-col gap-2 border-t-2 border-accent pt-4">
              <h3 className="text-body font-semibold text-text">Eval suites as CI gates</h3>
              <p className="text-body-sm text-text-secondary">
                Retrieval, generation faithfulness, agent trajectory, prompt-injection, and
                cross-tenant leakage suites run as gates in CI. Behavior has to clear their
                thresholds before it ships.
              </p>
            </article>
            <article className="flex flex-col gap-2 border-t-2 border-accent pt-4">
              <h3 className="text-body font-semibold text-text">Real cost, not estimates</h3>
              <p className="text-body-sm text-text-secondary">
                The dashboards show actual per-tenant cost, costed per message from real token
                usage - not a marketing figure. What you see is what a conversation cost.
              </p>
            </article>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="px-4 sm:px-8">
        <div className="mx-auto flex w-full max-w-[1080px] flex-col items-start gap-4 py-16 sm:items-center sm:py-20 sm:text-center">
          <h2 className="font-display text-title-1 font-semibold text-text">
            Trust it with your customers.
          </h2>
          <p className="max-w-[52ch] text-body text-text-secondary">
            Onboard your business and put a private, branded agent at your own address.
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
