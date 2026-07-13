# Demo Guide

A one-command script brings up the whole system locally - a real local GoTrue
(Supabase Auth), the database, the backend, the frontend, and a seeded demo
world with two tenants (a phone repair shop and a dental practice) plus three
login identities. No hosted Supabase project or paid API key is required to
walk the demo; live chat needs an LLM key (free-tier works) but the seeded
transcripts do not depend on one.

## One command

```bash
./scripts/demo.sh
```

It checks prerequisites (Docker, uv, npm), fixes `backend/.env` and
`frontend/.env.local` if needed, starts the db + local GoTrue + an nginx
auth-proxy, runs migrations and the demo-world seed, and brings up the backend
(on :8000) and frontend (on :3000) dev servers. Ctrl-C stops both dev servers;
the db and auth stay up for a quick rerun (`docker compose down` tears them out
fully). The first run downloads the local embedder model - this can take a
minute.

When it finishes you'll see the banner with the three URLs and credentials
below.

## URLs and credentials

Password is `wren-demo` for every identity.

| Surface | URL | Login |
|---|---|---|
| Customer chat (Bytefix) | http://bytefix.localhost:3000 | none |
| Customer chat (Lumident) | http://lumident.localhost:3000 | none |
| Tenant console | http://app.localhost:3000/login | owner@bytefix.dev |
| Tenant console | http://app.localhost:3000/login | owner@lumident.dev |
| Platform admin | http://admin.localhost:3000 | founder@wren.dev |

`*.localhost` subdomains resolve automatically in modern browsers. If yours
doesn't, add `127.0.0.1 bytefix.localhost lumident.localhost app.localhost
admin.localhost` to `/etc/hosts`.

## The 10-minute walkthrough

1. **Customer chat - Bytefix** (http://bytefix.localhost:3000, no login).
   Tap a starter chip ("How much is a screen replacement?") and get a grounded
   answer with citations from the seeded policy/price-list docs. Ask "How much
   for a flagship screen quote?" and get a deterministic QuoteCard (the agent
   picks the rule; the pricing engine computes the total - no model ever
   produces a dollar amount). Type "I'd like to speak to a human" and watch the
   escalation banner permanently replace the composer.

2. **Tenant console - Bytefix** (http://app.localhost:3000/login,
   owner@bytefix.dev / wren-demo). Open **Conversations** and click into a
   seeded transcript: the trace view shows the inspection verdicts (grounding,
   policy, injection - each pass/fail with a reason), the tool calls the agent
   made (search_knowledge, get_quote_inputs, lookup_order_or_ticket), and the
   per-message cost. Open **Escalations**: claim the seeded open escalation,
   type a reply, resolve it, then reload the customer chat to see your reply
   land in the transcript. Browse **Knowledge** (seeded policy/FAQ/price-list
   docs), **Pricing** (edit a price inline - typed in dollars, stored in exact
   cents), and **Onboarding**.

3. **Platform admin** (http://admin.localhost:3000, founder@wren.dev /
   wren-demo). The metrics bar and the tenants table show both Bytefix and
   Lumident with non-zero conversation counts and cost. Use the provision
   modal to create a new tenant live - it appears as `provisioning` (an honest,
   documented state: a platform-provisioned tenant has no owner yet until the
   claim mechanism is built; see `backend/app/api/platform.py`'s docstring).
   Suspend Lumident and reload http://lumident.localhost:3000 to see the
   customer surface react; reactivate it.

4. **Tenant console - Lumident** (http://app.localhost:3000/login,
   owner@lumident.dev / wren-demo). Same console, dental data - cleaning,
   whitening, fillings, crowns. This is the domain-agnostic proof: identical
   code, only `tenant_config` and uploaded knowledge differ from Bytefix.

5. **Live signup** (optional). http://app.localhost:3000/signup - because
   GoTrue is configured with autoconfirm, a brand-new business signs up and
   immediately lands in onboarding with zero founder intervention.

## How auth works locally

The script starts a real GoTrue (Supabase Auth) container that runs its own
migrations into the `auth` schema of the same `wren` database the app uses
(schema isolation is clean - the app's migrate runner and RLS live in
`public`; the app role has no grants on `auth`). An nginx shim on port 54321
strips the `/auth/v1` prefix that supabase-js hardcodes (hosted Supabase's Kong
gateway does this in production), so the frontend's supabase-js talks to real
GoTrue with zero frontend code changes. The anon key in
`frontend/.env.local` is minted at bootstrap from `backend/.env`'s
`SUPABASE_JWT_SECRET` (seeds/supabase_keys.py), so GoTrue signing and the
backend's `verify_token` always agree. Backend auth code is unchanged -
GoTrue-issued access tokens carry exactly `HS256 + aud=authenticated + exp +
sub`, which is what `verify_token` already checks.

## Troubleshooting

- **Free-tier LLM 429s during live chat.** Seeded transcripts keep the whole
  demo working without a live model. To enable live chat, set `LLM_PROVIDER`,
  `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` in `backend/.env` (see
  `.env.example` for free OpenRouter/Groq options; the model must support
  structured outputs).
- **Docker not running.** Start Docker Desktop and re-run the script.
- **Port 54321 in use.** This usually means a supabase CLI stack is running
  (`supabase_kong_*` on 54321). Stop it (`docker stop supabase_kong_*`) and
  re-run - the demo's auth-proxy needs 54321.
- **First-run embedder download.** The local embedder (`BAAI/bge-small-en-v1.5`,
  ~100MB) downloads on the first seed run. It's cached afterward.
- **`*.localhost` not resolving.** See the `/etc/hosts` note above.
- **Reset the whole world.** `docker compose down -v` (drops the DB volume too)
  then `./scripts/demo.sh`.
- **GoTrue migration corruption** (e.g. after a JWT-secret or image change
  against an old volume). Drop and recreate the auth schema, then rerun:
  `docker compose exec db psql -U postgres -d wren -c "drop schema if exists
  auth cascade; create schema auth;"` - GoTrue re-runs its migrations on next
  start.
- **`docker compose up -d db` alone still works.** The auth services are
  additive; you can run just the database for normal backend development
  exactly as before.
