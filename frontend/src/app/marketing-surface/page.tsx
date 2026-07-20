import { headers } from "next/headers";
import { surfaceUrl } from "@/lib/tenant";
import { Icon } from "@/components/ui/Icon";

/**
 * The landing page at the bare apex (wren.app / localhost:3000). Presents the
 * product and routes each visitor profile to its own front door: business
 * owners to the tenant-admin signup/login (app.*), customers to a live demo
 * tenant ({slug}.*), the platform operator to admin.*. Copy sticks to real
 * mechanics - no invented numbers or testimonials (phase-4 accept rule).
 */

/** Persistently seeded demo tenant (T-010 / seed_demo.py) - the live demo link. */
const DEMO_SLUG = "bytefix";

const STEPS = [
  {
    title: "Describe your business",
    body: "A short conversation extracts your services, prices, and policies into structured config - you review and confirm every field before anything goes live.",
  },
  {
    title: "Upload what you know",
    body: "Price lists, policies, FAQs - your documents become the only knowledge your agent answers from, with citations back to the source.",
  },
  {
    title: "Share your address",
    body: "Customers chat at your own subdomain, in your branding. You watch every conversation from your console and can take over any time.",
  },
];

const PRINCIPLES = [
  {
    title: "Citations, not vibes",
    body: "Every answer is grounded in your own documents and cites them. If your knowledge does not cover a question, the agent says so instead of guessing.",
  },
  {
    title: "Prices are computed, never guessed",
    body: "The model only selects services and quantities. A deterministic pricing engine does all arithmetic in exact cents, and a validation gate rejects any figure it did not compute.",
  },
  {
    title: "Humans stay in the loop",
    body: "Low confidence, frustration, or a request for a person hands the conversation to you - and the AI stops replying the moment it does.",
  },
];

export default async function MarketingHome() {
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
            AI support &amp; sales for any small business
          </p>
          <h1 className="max-w-[22ch] text-balance font-display text-display font-bold text-text">
            Give your business its own AI agent.
          </h1>
          <p className="max-w-[62ch] text-body-lg text-text-secondary">
            Wren onboards your business through a conversation and puts a private, branded
            assistant at your own address. It recommends, answers from your knowledge with
            citations, produces exact quotes, and brings in a human when it should.
          </p>
          <div className="flex flex-col gap-3 sm:flex-row">
            <a
              href={businessSignup}
              className="inline-flex items-center justify-center rounded-md border border-transparent bg-accent px-5 py-2.5 text-body font-medium text-text-inverse transition-colors duration-fast hover:bg-accent-hover active:bg-accent-active"
            >
              Create your agent
            </a>
            <a
              href={demoChat}
              className="inline-flex items-center justify-center rounded-md border border-border bg-surface px-5 py-2.5 text-body font-medium text-text transition-colors duration-fast hover:bg-surface-sunken"
            >
              Try the live demo
            </a>
          </div>
        </div>
      </section>

      {/* Profile router - one front door per kind of user */}
      <section aria-labelledby="front-doors" className="px-4 sm:px-8">
        <div className="mx-auto w-full max-w-[1080px] pb-16 sm:pb-24">
          <h2 id="front-doors" className="mb-6 font-display text-title-2 font-semibold text-text">
            One product, three front doors
          </h2>
          <div className="grid gap-4 sm:grid-cols-3">
            <article className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-6 shadow-1 transition-shadow duration-fast hover:shadow-2">
              <span
                aria-hidden="true"
                className="flex h-10 w-10 items-center justify-center rounded-md bg-accent-subtle text-accent"
              >
                <Icon name="rocket_launch" size={22} />
              </span>
              <h3 className="text-title-3 font-semibold text-text">I run a business</h3>
              <p className="flex-1 text-body-sm text-text-secondary">
                Onboard in minutes, upload your knowledge, set your prices, and watch every
                conversation from your own console.
              </p>
              <div className="flex flex-col items-start gap-2">
                <a
                  href={businessSignup}
                  className="text-body-sm font-medium text-accent underline-offset-2 hover:underline"
                >
                  Start onboarding
                </a>
                <a
                  href={businessLogin}
                  className="text-body-sm font-medium text-accent underline-offset-2 hover:underline"
                >
                  Sign in to your console
                </a>
              </div>
            </article>

            <article className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-6 shadow-1 transition-shadow duration-fast hover:shadow-2">
              <span
                aria-hidden="true"
                className="flex h-10 w-10 items-center justify-center rounded-md bg-accent-subtle text-accent"
              >
                <Icon name="forum" size={22} />
              </span>
              <h3 className="text-title-3 font-semibold text-text">I&apos;m a customer</h3>
              <p className="flex-1 text-body-sm text-text-secondary">
                No account, no app. You chat at the business&apos;s own address, in their branding
                - try it against our demo repair shop.
              </p>
              <div className="flex flex-col items-start gap-2">
                <a
                  href={demoChat}
                  className="text-body-sm font-medium text-accent underline-offset-2 hover:underline"
                >
                  Chat with the demo shop
                </a>
              </div>
            </article>

            <article className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-6 shadow-1 transition-shadow duration-fast hover:shadow-2">
              <span
                aria-hidden="true"
                className="flex h-10 w-10 items-center justify-center rounded-md bg-accent-subtle text-accent"
              >
                <Icon name="verified_user" size={22} />
              </span>
              <h3 className="text-title-3 font-semibold text-text">I operate the platform</h3>
              <p className="flex-1 text-body-sm text-text-secondary">
                Provision tenants, suspend or reactivate them, and watch per-tenant
                conversations and cost from the admin console.
              </p>
              <div className="flex flex-col items-start gap-2">
                <a
                  href={platformLogin}
                  className="text-body-sm font-medium text-accent underline-offset-2 hover:underline"
                >
                  Platform sign in
                </a>
              </div>
            </article>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section aria-labelledby="how-it-works" className="border-y border-border bg-surface-sunken px-4 sm:px-8">
        <div className="mx-auto w-full max-w-[1080px] py-16 sm:py-20">
          <h2 id="how-it-works" className="mb-6 font-display text-title-2 font-semibold text-text">
            How it works
          </h2>
          <ol className="grid gap-6 sm:grid-cols-3">
            {STEPS.map((step, i) => (
              <li key={step.title} className="flex flex-col gap-2">
                <span
                  aria-hidden="true"
                  className="flex h-8 w-8 items-center justify-center rounded-full bg-accent-container font-display text-body font-semibold text-text-inverse"
                >
                  {i + 1}
                </span>
                <h3 className="text-body font-semibold text-text">{step.title}</h3>
                <p className="text-body-sm text-text-secondary">{step.body}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* Why trust it */}
      <section aria-labelledby="principles" className="px-4 sm:px-8">
        <div className="mx-auto w-full max-w-[1080px] py-16 sm:py-20">
          <h2 id="principles" className="mb-6 font-display text-title-2 font-semibold text-text">
            Built to be trusted with your customers
          </h2>
          <div className="grid gap-6 sm:grid-cols-3">
            {PRINCIPLES.map((p) => (
              <article key={p.title} className="flex flex-col gap-2 border-t-2 border-accent pt-4">
                <h3 className="text-body font-semibold text-text">{p.title}</h3>
                <p className="text-body-sm text-text-secondary">{p.body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>
    </>
  );
}
