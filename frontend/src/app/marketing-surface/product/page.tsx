import type { Metadata } from "next";
import { headers } from "next/headers";
import { surfaceUrl } from "@/lib/tenant";
import { Icon } from "@/components/ui/Icon";
import type { IconName } from "@/components/ui/Icon";

/**
 * /product - the mechanics tour. One agent surfaced through three front doors
 * (customer chat, tenant console, platform console), then the four properties
 * that hold it together. Copy sticks to mechanics that exist in this repo -
 * no invented numbers or testimonials (phase-4 accept rule).
 */

/** Persistently seeded demo tenant (T-010 / seed_demo.py) - the live demo link. */
const DEMO_SLUG = "bytefix";

export const metadata: Metadata = {
  title: "Product - Wren",
  description:
    "One agent, three front doors: a branded customer chat that cites your documents and quotes exact prices, a tenant console to run it, and a platform console to operate the fleet.",
};

interface Differentiator {
  icon: IconName;
  title: string;
  body: string;
}

const DIFFERENTIATORS: Differentiator[] = [
  {
    icon: "verified_user",
    title: "Cited answers",
    body: "Every reply is grounded in your own uploaded documents and links back to the source. If your knowledge does not cover a question, the agent says so instead of guessing.",
  },
  {
    icon: "sell",
    title: "Deterministic quotes",
    body: "The model only selects rules, items, and quantities. A pricing engine computes every total in integer cents, and a validation layer rejects any monetary figure the engine did not produce.",
  },
  {
    icon: "support_agent",
    title: "Human escalation",
    body: "Low confidence, customer frustration, or an explicit request hands the conversation to a person, and the AI stops replying the moment it does. Your team answers from the console.",
  },
  {
    icon: "groups",
    title: "Domain-agnostic by construction",
    body: "No code branches on a business vertical anywhere. All behavior comes from tenant config and uploaded knowledge, so a dentist and a phone-repair shop run identical code.",
  },
];

const UNDER_THE_HOOD = [
  {
    title: "Per-message traces",
    body: "Every message records the tool calls the agent made, the inspection verdicts (grounding, policy, injection - each pass or fail with a reason), and its own cost. Nothing is a black box in your console.",
  },
  {
    title: "Real cost accounting",
    body: "Token usage is costed per message and rolled up per tenant, so the dashboards show what a conversation actually cost - measured, not a marketing estimate.",
  },
  {
    title: "CI-gated evals",
    body: "Retrieval, generation faithfulness, agent trajectory, prompt-injection, and cross-tenant leakage suites run as gates in CI. Behavior is held to thresholds before it ships, not asserted after.",
  },
];

export default async function ProductPage() {
  const host = (await headers()).get("host") ?? "";
  const businessSignup = surfaceUrl({ surface: "tenant-admin" }, host, "/signup");
  const businessLogin = surfaceUrl({ surface: "tenant-admin" }, host, "/login");
  const platformLogin = surfaceUrl({ surface: "platform" }, host, "/login");
  const demoChat = surfaceUrl({ surface: "customer", slug: DEMO_SLUG }, host);

  return (
    <>
      {/* Hero */}
      <section className="px-4 sm:px-8">
        <div className="mx-auto flex w-full max-w-[1080px] flex-col items-start gap-6 py-16 sm:items-center sm:py-24 sm:text-center">
          <p className="rounded-full border border-border bg-surface px-3 py-1 text-footnote font-medium text-text-secondary">
            Product
          </p>
          <h1 className="max-w-[20ch] text-balance font-display text-display font-bold text-text">
            One agent, three front doors.
          </h1>
          <p className="max-w-[62ch] text-body-lg text-text-secondary">
            The same agent shows up as a branded chat for your customers, a console for the
            business running it, and an operations console for the platform. Each surface is a
            different view of one system - the mechanics below are what makes it trustworthy.
          </p>
        </div>
      </section>

      {/* Band 1 - Customer chat */}
      <section
        aria-labelledby="door-customer"
        className="border-y border-border bg-surface-sunken px-4 sm:px-8"
      >
        <div className="mx-auto grid w-full max-w-[1080px] items-center gap-8 py-16 sm:py-20 md:grid-cols-2">
          <div className="flex flex-col gap-4">
            <span
              aria-hidden="true"
              className="flex h-11 w-11 items-center justify-center rounded-md bg-accent-subtle text-accent"
            >
              <Icon name="forum" size={24} />
            </span>
            <h2 id="door-customer" className="font-display text-title-2 font-semibold text-text">
              Customer chat
            </h2>
            <p className="text-body text-text-secondary">
              Customers chat at the business&apos;s own address, in its branding, with no account.
              Answers cite the source document. When a customer asks for a price, they get a
              deterministic quote card - the agent selected the rule, the engine computed the
              total. Asking for a person raises an escalation banner that replaces the composer.
            </p>
            <a
              href={demoChat}
              className="inline-flex items-center gap-1.5 self-start text-body-sm font-medium text-accent underline-offset-2 hover:underline"
            >
              Try the live demo chat
              <Icon name="arrow_forward" size={16} />
            </a>
          </div>
          <ul className="flex flex-col gap-3">
            {[
              "Grounded answers with citations back to your documents",
              "Deterministic quote cards computed in exact cents",
              "A permanent escalation banner the moment a human takes over",
            ].map((line) => (
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

      {/* Band 2 - Tenant console */}
      <section aria-labelledby="door-console" className="px-4 sm:px-8">
        <div className="mx-auto grid w-full max-w-[1080px] items-center gap-8 py-16 sm:py-20 md:grid-cols-2">
          <ul className="order-2 flex flex-col gap-3 md:order-1">
            {[
              "Onboarding that extracts your services and policies into reviewable config",
              "Knowledge: the uploaded documents your agent answers from",
              "Conversations with a full per-message trace and cost",
              "Escalations you claim, reply to, and resolve",
              "Pricing rules edited in dollars, stored in exact cents",
              "Dashboards for real per-tenant cost and eval status",
            ].map((line) => (
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
          <div className="order-1 flex flex-col gap-4 md:order-2">
            <span
              aria-hidden="true"
              className="flex h-11 w-11 items-center justify-center rounded-md bg-accent-subtle text-accent"
            >
              <Icon name="dashboard" size={24} />
            </span>
            <h2 id="door-console" className="font-display text-title-2 font-semibold text-text">
              Tenant console
            </h2>
            <p className="text-body text-text-secondary">
              The business runs its agent from a single console: onboard, upload knowledge, watch
              every conversation with its trace, handle escalations, set prices, and read the
              dashboards. You can take over any conversation at any time.
            </p>
            <div className="flex flex-col items-start gap-2">
              <a
                href={businessSignup}
                className="inline-flex items-center gap-1.5 text-body-sm font-medium text-accent underline-offset-2 hover:underline"
              >
                Start onboarding
                <Icon name="arrow_forward" size={16} />
              </a>
              <a
                href={businessLogin}
                className="text-body-sm font-medium text-accent underline-offset-2 hover:underline"
              >
                Sign in to your console
              </a>
            </div>
          </div>
        </div>
      </section>

      {/* Band 3 - Platform console */}
      <section
        aria-labelledby="door-platform"
        className="border-y border-border bg-surface-sunken px-4 sm:px-8"
      >
        <div className="mx-auto grid w-full max-w-[1080px] items-center gap-8 py-16 sm:py-20 md:grid-cols-2">
          <div className="flex flex-col gap-4">
            <span
              aria-hidden="true"
              className="flex h-11 w-11 items-center justify-center rounded-md bg-accent-subtle text-accent"
            >
              <Icon name="verified_user" size={24} />
            </span>
            <h2 id="door-platform" className="font-display text-title-2 font-semibold text-text">
              Platform console
            </h2>
            <p className="text-body text-text-secondary">
              Whoever operates the platform provisions new tenants, suspends or reactivates them,
              and watches per-tenant conversation counts and cost from one place. Every tenant&apos;s
              data stays isolated behind row-level security.
            </p>
            <a
              href={platformLogin}
              className="text-body-sm font-medium text-text-secondary underline-offset-2 hover:text-text hover:underline"
            >
              Platform operator sign-in
            </a>
          </div>
          <ul className="flex flex-col gap-3">
            {[
              "Provision a tenant live from the console",
              "Suspend or reactivate a tenant and watch its chat react",
              "Per-tenant conversation counts and real cost",
            ].map((line) => (
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

      {/* Differentiators bento */}
      <section aria-labelledby="differentiators" className="px-4 sm:px-8">
        <div className="mx-auto w-full max-w-[1080px] py-16 sm:py-20">
          <h2
            id="differentiators"
            className="mb-6 font-display text-title-2 font-semibold text-text"
          >
            Four properties, everywhere
          </h2>
          <div className="grid gap-4 sm:grid-cols-2">
            {DIFFERENTIATORS.map((d) => (
              <article
                key={d.title}
                className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-6 shadow-1 transition-shadow duration-fast hover:shadow-2"
              >
                <span
                  aria-hidden="true"
                  className="flex h-10 w-10 items-center justify-center rounded-md bg-accent-subtle text-accent"
                >
                  <Icon name={d.icon} size={22} />
                </span>
                <h3 className="text-title-3 font-semibold text-text">{d.title}</h3>
                <p className="text-body-sm text-text-secondary">{d.body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* Under the hood */}
      <section
        aria-labelledby="under-the-hood"
        className="border-y border-border bg-surface-sunken px-4 sm:px-8"
      >
        <div className="mx-auto w-full max-w-[1080px] py-16 sm:py-20">
          <h2
            id="under-the-hood"
            className="mb-2 font-display text-title-2 font-semibold text-text"
          >
            Under the hood, honestly
          </h2>
          <p className="mb-6 max-w-[62ch] text-body text-text-secondary">
            The claims above are only as good as what you can inspect. Three things make them
            checkable rather than marketing.
          </p>
          <div className="grid gap-6 sm:grid-cols-3">
            {UNDER_THE_HOOD.map((item) => (
              <article
                key={item.title}
                className="flex flex-col gap-2 border-t-2 border-accent pt-4"
              >
                <h3 className="text-body font-semibold text-text">{item.title}</h3>
                <p className="text-body-sm text-text-secondary">{item.body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="px-4 sm:px-8">
        <div className="mx-auto flex w-full max-w-[1080px] flex-col items-start gap-4 py-16 sm:items-center sm:py-20 sm:text-center">
          <h2 className="font-display text-title-1 font-semibold text-text">
            Give your business its own agent.
          </h2>
          <p className="max-w-[52ch] text-body text-text-secondary">
            Onboard through a conversation and put a private, branded assistant at your own address.
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
