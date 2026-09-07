# Agencx - Database Design

The implementation truth for schema shape. Supabase Postgres 15+ with `pgvector`.
The tables below are the shipped Wren schema (migrations `backend/migrations/`
are the source of truth; SQL shown is the contract shape). Agencx additions are
marked **NEW**; everything else exists and is carried forward.

## 1. Principles (apply to every table and migration)

1. **RLS on every tenant-scoped table, enforced AND forced.** Every table with
   `tenant_id` gets `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` -
   `FORCE` matters because on Supabase the `postgres` role owns tables and would
   silently bypass RLS otherwise.
2. **Integer cents everywhere.** No `numeric`, floats, or dollar columns. Every
   monetary column is `*_cents integer`. The one exception is `cost_logs.cost_usd`
   (observability metadata, never customer-facing pricing).
3. **Domain-agnostic names only.** Columns describe generic concepts (items,
   rules, kinds, refs). A column that only makes sense for one vertical belongs
   in a `jsonb` config/attributes value instead (I8).
4. **Denormalized `tenant_id` on `messages` and `tool_calls`.** RLS can then
   check it directly instead of joining through the parent.
5. **Quotes are immutable once sent.** Only `status` may change after insert.
   Enforced by trigger.
6. **Text + CHECK instead of native enums.** Easier to evolve in migrations,
   equally safe.
7. **UUID primary keys** via `gen_random_uuid()`. Timestamps are `timestamptz`,
   default `now()`.

## 2. Roles and tenant context

### 2.1 Connection roles

The role names keep the Wren code names (standing names note in the set README).

| Role | Used by | Properties |
|---|---|---|
| `postgres` (Supabase-managed) | migrations only | table owner; FORCE RLS still applies to it |
| `wren_app` | the FastAPI backend (its only DB identity) | `LOGIN`, no `BYPASSRLS`, granted CRUD on app tables |
| `wren_resolver` | owns `resolve_tenant_slug` only | `NOLOGIN`, `BYPASSRLS` - the single, audited RLS bypass in the system |

### 2.2 Tenant context (the RLS key)

The backend sets two transaction-local settings before any query runs (FastAPI
middleware):

```sql
select set_config('app.tenant_id', :tenant_id, true);  -- '' when none resolved
select set_config('app.role', :role, true);            -- 'customer' | 'tenant_admin' | 'staff' | 'platform_admin' | 'service'
```

`'service'` is the backend acting for itself in exactly one flow: the signup
transaction. Its powers are the Shape C policies below and nothing else.
`'staff'` is the member role the 0025 policies branch on (F-3, G3.1): staff
reaches the conversation work surface only - see section 2.3's staff shapes.
The owner-to-`tenant_admin` / staff-to-`staff` mapping lives in exactly one
place, `shared/auth.py` (`_RLS_ROLE`); the SQL never re-derives it.

Helper functions every policy uses (`app_tenant_id()`, `app_is_platform_admin()`,
`app_is_service()`, and 0025's `app_role()`) are defined in migrations
`0001_extensions.sql` and `0025_schema_cleanup.sql`.

### 2.3 The standard policy shapes

```sql
-- Shape A: tenant-scoped table (the default for everything below)
alter table <t> enable row level security;
alter table <t> force row level security;

create policy tenant_isolation on <t>
  for all
  using (tenant_id = app_tenant_id())
  with check (tenant_id = app_tenant_id());

create policy platform_admin_read on <t>
  for select
  using (app_is_platform_admin());
```

Platform-admin access is read-only through policies plus explicit writes on
`tenants`/`platform_admins` only.

**Shape A since 0025 (F-3):** the `tenant_isolation` policies branch on role.
Admin tables (`tenant_config`, `documents`, `knowledge_chunks`, `offerings`,
`pricing_rules`, `tenant_assets`, `users`, `tenant_media`) keep the tenant's
read for `tenant_admin` and `customer` (chat, retrieval and the storefront
read them under the customer context) but require `tenant_admin` to write -
the with-check no longer permits customer writes. `tenants` is special-cased
(the `id` column is the tenant identifier) with the same branch.

```sql
-- Shape D (0025): staff's narrow slice on the conversation tables.
-- RLS evaluates policies per command with OR semantics, so per-command
-- policies coexist with Shape A's for-all and the platform/service shapes.

-- conversations: staff reads; staff flips status human <-> open only.
create policy staff_read on conversations for select
  using (tenant_id = app_tenant_id() and app_role() = 'staff');
create policy staff_takeover on conversations for update
  using (tenant_id = app_tenant_id() and app_role() = 'staff')
  with check (tenant_id = app_tenant_id() and app_role() = 'staff'
              and status in ('human', 'open'));

-- messages: staff reads; staff inserts only human_agent replies and the
-- takeover/system stamp (never customer or assistant rows).
create policy staff_conversation_write on messages for insert
  with check (tenant_id = app_tenant_id() and app_role() = 'staff'
              and role in ('human_agent', 'system'));

-- escalations: staff reads; staff claims and resolves.
create policy staff_claim on escalations for update
  using (tenant_id = app_tenant_id() and app_role() = 'staff')
  with check (tenant_id = app_tenant_id() and app_role() = 'staff'
              and status in ('claimed', 'resolved'));

-- tool_calls, quotes, orders, cost_logs, eval_runs: staff_read (select) only.
```

Staff gets no DELETE anywhere - no staff policy grants it, so a staff DELETE
matches zero rows. The endpoint layer mirrors the same line:
`require_owner` guards the settings/knowledge/offerings/pricing/onboarding
routers; conversations/escalations/dashboards pass the caller's role into
their `tenant_context` (shared/auth.py `require_owner`, F-3).

```sql
-- Shape B: platform-global table (no tenant_id): platform_admins; tenants is special-cased
-- Shape C: service role (signup transaction only). Applied to exactly three
-- tables - tenants, tenant_config, users - and only for INSERT:
create policy service_signup_insert on <t>
  for insert
  with check (app_is_service());
```

**Leakage test rule:** with `app.tenant_id` set to tenant A, every query against
every tenant-scoped table must return zero tenant-B rows - including through
joins, retrieval, and tool paths.

## 3. Tenancy and identity

```sql
create table tenants (
  id          uuid primary key default gen_random_uuid(),
  slug        text not null unique check (slug ~ '^[a-z0-9](-?[a-z0-9])*$' and length(slug) between 3 and 40),
  name        text not null,
  status      text not null default 'active' check (status in ('provisioning', 'active', 'suspended')),
  business_name text,                                    -- migration 0014
  payment_processing_mode text not null default 'DIRECT' -- 'PLATFORM' | 'DIRECT' | 'DEFERRED' (0014)
    check (payment_processing_mode in ('PLATFORM', 'DIRECT', 'DEFERRED')),
  created_at  timestamptz not null default now()
);
```

Policies: `tenant_self_read` (select own row), `tenant_self_update` (update own
row, migration 0014), `platform_admin_all`, `service_signup_insert`.

```sql
create table tenant_config (
  tenant_id             uuid primary key references tenants(id) on delete cascade,
  system_prompt         text not null default '',  -- RETIRED, see below
  tone                  text not null default 'friendly',  -- RETIRED, see below
  enabled_tools         jsonb not null default '[...]',   -- the per-tenant tool set (D-1)
  brand                 jsonb not null default '{}',   -- {"accent":"#RRGGBB","logo_url":...,"display_name":...}
  config                jsonb not null default '{}',   -- onboarding business/hours/services/tax fields (written by the confirm flow)
  updated_at            timestamptz not null default now()
);
```

**RETIRED (W-9):** `system_prompt` and `tone` are written by the confirm path
and the seeds but read by no application code. What the customer assistant is
told about itself is now `app/agents/contract.py`, one code-owned contract on
every prose route, and how it sounds is the structured `config->customer_voice`
(`{"preset": ..., "custom_style": ...}`) that migration `0027` back-filled from
`tone`. Both columns are dropped by W-10
(`docs/agencx/spec/active/14-schema-drop.md`), not by `0027`.

**CHANGING (D-1, D-2):** `enabled_tools` defaults to the full advanced set today
(`["search_knowledge","recommend_items","lookup_order_or_ticket","get_quote_inputs","create_escalation"]`).
The Agencx lean default changes the default to `["answer_from_knowledge","create_escalation"]`
and the new-tenant/legacy backfill is a migration in D-2. The tool registry is
built from this column.

```sql
create table users (
  id          uuid primary key,                        -- = Supabase auth.users.id
  tenant_id   uuid not null references tenants(id) on delete cascade,
  role        text not null default 'owner' check (role in ('owner', 'staff')),
  created_at  timestamptz not null default now()
);
```

```sql
create table platform_admins (
  user_id     uuid primary key,                        -- = Supabase auth.users.id
  created_at  timestamptz not null default now()
);
```

### Business assets (E-6; **NEW**, migration 0021 - undocumented until now)

```sql
create table tenant_assets (
  tenant_id   uuid not null references tenants(id) on delete cascade,
  kind        text not null check (kind in ('cover')),
  mime        text not null,
  bytes       bytea not null,
  updated_at  timestamptz not null default now(),
  primary key (tenant_id, kind)
);
```

Policies: `tenant_isolation` (owner, all ops), `platform_admin_read`, and
`service_read` - the anonymous public Booking page must be able to serve a
cover the same way it serves the tenant's name, so the unauthenticated
service role can select it. Kept out of `tenant_config` deliberately: `brand`/
`config` sit on the hot path (the public tenant lookup primes the chat's
context package, P-3), and a base64 image there would be a latency regression.

**`ponytail:`** the image lives in Postgres `bytea`, not object storage - one
small image per tenant, capped at 2MB by the API and resized client-side
before upload, fits a row fine and needs no new dependency or credential in
local dev (there was no object store available to every surface at the time).
`kind` is hard-CHECK-constrained to `'cover'` only, so this table cannot hold
a gallery as-is - **the upgrade path is D24/`M-2`** (`docs/agencx/spec/completed/11-offerings-media.md`),
which moves business media (a capped gallery + per-offering photos) to
Cloudinary and either widens or replaces this table.

### Login-in-chat (O-2; **auth_codes table dropped 2026-08-28, D23**)

O-2 shipped this table: a backend-issued, sha-256-hashed 6-digit code with a
TTL and an attempt budget, verified by `features/auth/controller.py`. The auth
migration (D23, `design/decisions.md`) replaced it with GoTrue's own OTP flow
(`signInWithOtp`/`verifyOtp`, type `email`) - GoTrue issues, mails and verifies
the code itself, so there is no code table on our side any more; migration
0022 drops it. Users still resolve to `auth.users.id` exactly as before -
login-in-chat remains the delivery mechanism; only the issuer changed.

### Slug resolution

```sql
create or replace function resolve_tenant_slug(p_slug text)
  returns table (id uuid, name text, status text, brand jsonb)
  language sql stable security definer set search_path = public as
$$ select t.id, t.name, t.status, coalesce(c.brand, '{}'::jsonb)
     from tenants t left join tenant_config c on c.tenant_id = t.id
    where t.slug = p_slug $$;
alter function resolve_tenant_slug(text) owner to wren_resolver;
revoke all on function resolve_tenant_slug(text) from public;
grant execute on function resolve_tenant_slug(text) to wren_app;
```

The unauthenticated customer surface must resolve a slug BEFORE any tenant
context exists; FORCE RLS binds even the table owner, so the resolver is owned
by `wren_resolver` (NOLOGIN, BYPASSRLS), SECURITY DEFINER, and returns only
public columns. Helper functions `resolve_user_tenant(p_user_id)` and
`resolve_platform_admin(p_user_id)` (migration 0009) back the auth middleware.

## 4. Knowledge and retrieval

```sql
create table documents (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null references tenants(id) on delete cascade,
  filename     text not null,
  doc_type     text not null check (doc_type in ('policy', 'faq', 'catalog', 'price_list', 'other', 'website')),
  status       text not null default 'pending' check (status in ('draft', 'pending', 'processing', 'ready', 'failed')),
  error        text,
  structured   jsonb,                                   -- 0019: the readable sections
  uploaded_at  timestamptz not null default now(),
  updated_at   timestamptz not null default now()       -- 0018: knowledge_version input
);
```

`website` (migration 0015) carries the URL-scrape ingest path, wired by O-3.

`draft` and `structured` (migration 0019, D19) are the review step: a source is
processed into `[{"heading", "body"}]` sections and held as a `draft` - no
chunks, so retrieval cannot reach it - until the owner saves it. Saving runs the
normal pipeline over the sections they approved. `structured` is null on rows
ingested before the knowledge screen existed; those are processed on first view
rather than backfilled, since the work costs a model call per document.

```sql
create table knowledge_chunks (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null references tenants(id) on delete cascade,
  document_id  uuid not null references documents(id) on delete cascade,
  content      text not null,
  embedding    vector(384),                             -- local bge-small-en-v1.5; Azure truncates to 384 (0010)
  metadata     jsonb not null default '{}',             -- {"source":filename,"chunk_index":n,...}
  tsv          tsvector generated always as (to_tsvector('english', content)) stored,
  created_at   timestamptz not null default now()
);
create index knowledge_chunks_tenant_idx    on knowledge_chunks (tenant_id, document_id);
create index knowledge_chunks_embedding_idx on knowledge_chunks using hnsw (embedding vector_cosine_ops);
create index knowledge_chunks_tsv_idx       on knowledge_chunks using gin (tsv);
```

**Every retrieval query still carries `where tenant_id = :tenant_id` explicitly**
- RLS is the net, not the filter; the explicit predicate lets the planner combine
the HNSW/GIN indexes with tenant scoping.

### knowledge_version (**NEW** - P-4)

No new table. `knowledge_version` is derived:

```sql
select greatest(
  coalesce((select max(updated_at) from documents where tenant_id = :tenant_id), 'epoch'::timestamptz),
  coalesce((select max(updated_at) from offerings where tenant_id = :tenant_id), 'epoch'::timestamptz),
  coalesce((select updated_at from tenant_config where tenant_id = :tenant_id), 'epoch'::timestamptz)
)
```

Any upload, re-ingest, status change, or a profile/system-prompt/brand write
to `tenant_config` bumps it (both tables have carried a touch trigger since
0003/0018). The context-package cache (architecture section 9) is keyed by
`(tenant_id, knowledge_version)`; a bumped version invalidates the cache on
the next lookup. `offerings.updated_at` is included because `M-1` lets owners
write it directly. Deletion also touches `tenant_config.updated_at`, because a
deleted offering no longer has an `updated_at` value for this formula to read.

## 5. Commerce (the deterministic-pricing tables; per-tenant optional in Agencx)

```sql
create table offerings (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null references tenants(id) on delete cascade,
  name         text not null,
  description  text not null default '',
  price_cents  integer check (price_cents is null or price_cents >= 0),  -- null = priced via a rule
  active       boolean not null default true,             -- false = retired, never deleted
  position     integer not null default 0,               -- M-4: the owner's storefront order
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
create index offerings_storefront_order on offerings (tenant_id, active, position, created_at);

create table pricing_rules (
  id                 uuid primary key default gen_random_uuid(),
  tenant_id          uuid not null references tenants(id) on delete cascade,
  code               text not null,                     -- stable selector the agent emits, e.g. 'catering-tray-m'
  label              text not null,
  unit_amount_cents  integer not null check (unit_amount_cents >= 0),
  unit               text not null default 'each',      -- display-only
  conditions         jsonb not null default '{}',       -- engine-interpreted
  active             boolean not null default true,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now(),
  unique (tenant_id, code)
);

create table quotes (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null references tenants(id) on delete cascade,
  conversation_id  uuid not null,
  foreign key (tenant_id, conversation_id) references conversations (tenant_id, id) on delete cascade,
  line_items       jsonb not null,
  subtotal_cents   integer not null check (subtotal_cents >= 0),
  tax_cents        integer not null default 0 check (tax_cents >= 0),
  total_cents      integer not null check (total_cents = subtotal_cents + tax_cents),
  status           text not null default 'draft' check (status in ('draft', 'sent', 'expired')),
  created_at       timestamptz not null default now()
);
```

All Shape A. **Only the pricing engine writes `quotes`** - it computes
`line_items/subtotal/tax/total`; no other code path constructs those values. In
Agencx these tables exist but are dormant for lean tenants (D-1): the engine
runs only when quoting is enabled, and the quote tools are absent from the
enabled set.

## 6. Conversations and operations

```sql
create table conversations (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references tenants(id) on delete cascade,
  customer_ref  text,                                   -- anonymous session id or handle; no auth at core scope
  channel       text not null default 'web' check (channel in ('web')),
  status        text not null default 'open' check (status in ('open', 'escalated', 'closed')),
  created_at    timestamptz not null default now(),
  unique (tenant_id, id)     -- composite-FK target
);

create table messages (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null references tenants(id) on delete cascade,
  conversation_id  uuid not null,
  foreign key (tenant_id, conversation_id) references conversations (tenant_id, id) on delete cascade,
  unique (tenant_id, id),
  role             text not null check (role in ('customer', 'assistant', 'system', 'human_agent')),
  content          text not null,
  agent_node       text,                                -- which graph node authored it
  metadata         jsonb not null default '{}',         -- inspection verdicts (migration 0012)
  created_at       timestamptz not null default now()
);

create table tool_calls (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references tenants(id) on delete cascade,
  message_id  uuid not null,
  foreign key (tenant_id, message_id) references messages (tenant_id, id) on delete cascade,
  tool_name   text not null,
  arguments   jsonb not null default '{}',
  result      jsonb,
  success     boolean not null,
  latency_ms  integer,
  created_at  timestamptz not null default now()
);

create table orders (                                   -- mock order/ticket data, seeded per tenant
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references tenants(id) on delete cascade,
  ref_code      text not null,                          -- what a customer quotes back: 'R-1042'
  kind          text not null,                          -- tenant-defined: 'repair','order','booking'
  customer_ref  text,
  status        text not null,                          -- tenant-defined vocabulary, stored as data
  details       jsonb not null default '{}',
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  unique (tenant_id, ref_code)
);

create table escalations (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null references tenants(id) on delete cascade,
  conversation_id  uuid not null,
  foreign key (tenant_id, conversation_id) references conversations (tenant_id, id) on delete cascade,
  reason           text not null,
  status           text not null default 'open' check (status in ('open', 'claimed', 'resolved')),
  created_at       timestamptz not null default now(),
  resolved_at      timestamptz
);
create unique index escalations_open_conversation_idx   -- T-020: no duplicate open escalations
  on escalations (tenant_id, conversation_id) where status = 'open';
```

All Shape A.

## 7. Eval and cost

```sql
create table eval_runs (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references tenants(id) on delete cascade,
  run_type    text not null check (run_type in ('retrieval', 'generation', 'trajectory', 'injection', 'leakage', 'full')),
  metrics     jsonb not null,          -- {"recall_at_5":0.87,"mrr":...}
  git_sha     text not null default '',
  created_at  timestamptz not null default now()
);

create table cost_logs (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null references tenants(id) on delete cascade,
  conversation_id  uuid references conversations(id) on delete set null,
  model            text not null,
  input_tokens     integer not null default 0,
  output_tokens    integer not null default 0,
  cost_usd         numeric(12,6) not null default 0,   -- the one non-cents money column (observability only)
  created_at       timestamptz not null default now()
);
```

All Shape A. **CHANGING (P-2):** cost/tracing gains per-provider TTFT and
failover-event attributes (scalar-only; no cross-tenant content), so the
latency budget is observable in the dashboards. `eval_cases` was dropped by
0025 (F-3) - the eval runners' case source is the JSONL datasets and nothing
ever read the table back; `eval_runs` and `cost_logs` remain.

## 8. Triggers

```sql
-- updated_at maintenance (tenant_config, offerings, pricing_rules, orders)
create or replace function touch_updated_at() returns trigger language plpgsql as
$$ begin new.updated_at = now(); return new; end $$;

-- quote immutability: after insert, only draft->sent->expired status transitions
create or replace function quotes_immutable() returns trigger language plpgsql as
$$ ... raise exception 'quotes are immutable except status' ... $$;
create trigger quotes_immutable_trg before update on quotes for each row execute function quotes_immutable();
```

## 9. Migration order

One migration file per numbered step, `backend/migrations/NNNN_<name>.sql`,
applied in order by a plain runner (no heavy framework):

```
0001_extensions.sql        vector; helper functions; touch_updated_at
0002_roles.sql             wren_app role + default privileges; wren_resolver role
0003_tenancy.sql           tenants, tenant_config, users, platform_admins (+ RLS, resolve_tenant_slug)
0004_knowledge.sql         documents, knowledge_chunks (+ RLS, HNSW/GIN indexes)
0005_conversations.sql     conversations, messages, tool_calls (+ RLS)
0006_commerce.sql          catalog_items, pricing_rules, quotes (+ RLS, quotes_immutable)
0007_operations.sql        orders, escalations (+ RLS)
0008_eval_cost.sql         eval_runs, cost_logs (+ RLS); eval_cases dropped by 0025
0009_auth_lookup.sql       resolve_user_tenant, resolve_platform_admin
0010_embedding_dim.sql     embedding retarget to vector(384)
0011_escalations_dedupe.sql  unique open-escalation index
0012_messages_metadata.sql   messages.metadata jsonb
0013_platform_admin_tenant_config_write.sql  platform admin can write tenant_config
0014_onboarding_business_fields.sql  tenants.business_name, payment_processing_mode, tenant_self_update
0015_website_doc_type.sql  documents.doc_type 'website'
0016_enabled_tools_lean_default.sql  lean enabled_tools default + backfill (D-2)
0017_auth_codes.sql        auth_codes (login-in-chat, O-2) - dropped by 0022
0018_documents_updated_at.sql  documents.updated_at + touch trigger (P-4)
0019_documents_structured.sql  documents 'draft' status + structured jsonb (O-3/D19)
0020_conversation_human_takeover.sql  conversations.status splits 'open'/'human' (human takeover, C-6)
0021_tenant_assets.sql     tenant_assets (business cover photo, E-6) - see section 3
0022_drop_auth_codes.sql   drops auth_codes - login-in-chat moved to GoTrue OTP (D23)
0023_rename_catalog_items_to_offerings.sql  names the M-1 writer's table after the Offering domain noun
0024_offering_position.sql  offerings.position - the order the owner puts their storefront list in (M-4)
0025_schema_cleanup.sql   drops dead schema, adds app_role()/staff RLS, offerings.category and tenant_media (F-3/M-2)
0026_documents_offerings.sql  documents.offerings - candidates extracted once at ingest, not re-derived per read (W-6)
0027_customer_voice.sql    back-fills config->customer_voice from the tone column (W-9); drops no column
```

Shipped Agencx migration: `0025_schema_cleanup.sql` (`M-2`,
`docs/agencx/spec/completed/11-offerings-media.md`, D24) adds `tenant_media` for the
Cloudinary-backed cover and per-offering visuals while retaining legacy
`tenant_assets` reads during rollout.

Every table migration ends with its RLS + policies + grants to `wren_app`. A
table without RLS must never survive a migration - the schema audit enforces
this.

## 10. Seed plan

`backend/seeds/` (idempotent scripts, runnable per environment):

- `seed_tenant1_phoneshop.py` - Tenant 1 (anchor): slug `bytefix`, config (tone,
  tax), ~15 categorized offerings, ~12 pricing_rules, ~20 mock orders, knowledge
  docs via the real ingestion pipeline. Seeded already-onboarded: `business_name`,
  persona `system_prompt`, and a completed `config->'onboarding'` record + `profile`
  written exactly as the confirm flow leaves them, so the demo tenant skips the
  interview.
- `seed_tenant2_dental.py` - Tenant 2 (generalization proof): created only
  through the conversational onboarding flow + uploads; holds raw input
  documents and the interview script, and one deliberate direct
  `tenant_config` update (the v3 onboarding draft, per the 2026-07-30 ADR).
- `seed_leakage_pair.py` - two throwaway tenants with disjoint secret facts for
  the leakage test.
- `seed_injection_probe.py` - one throwaway tenant with poisoned knowledge for
  the injection eval.
- `seed_demo.py` - the demo world: both anchor tenants (each pre-onboarded like
  tenant 1), GoTrue auth users, membership (`users` owners + the founder's
  `platform_admins` row), and conversations/tool calls/cost logs/escalations.
- `_helpers.py` - shared pool/wipe/tenant-core/commerce/knowledge helpers the
  direct-DB seeds use (F-3). `insert_tenant_core`'s `profile` argument writes
  the pre-onboarded end-state from the same onboarding dataclasses the confirm
  path uses.

Agencx adds the Sababa anchor seed in O-3/O-4 work (menu + catering-rate + FAQ
documents through the real upload + ingestion path), aligned with the reference
tenant 1 in the PRD.

## 11. Schema audit (runs in CI)

A test queries `pg_tables`/`pg_policies` and asserts: every table with a
`tenant_id` column has RLS enabled and forced with at least the `tenant_isolation`
policy; every monetary column matches `%_cents` and is integer-typed
(`cost_logs.cost_usd` is the single allowed exception); the teeth test drops a
policy on a throwaway branch and must go red.
