# WREN - Database Design

> **Derived from:** Architecture Doc section 3 (data model), section 7 (security), PRD MUSTs M1/M2/M8/M14. **Precedence:** this file is the implementation truth for schema shape; the Architecture Doc wins on scope. **Read via:** the read-list on your ticket - most tickets need only one or two sections here.
> Target: Supabase Postgres 15+ with `pgvector`. All SQL below is meant to be pasted into migrations nearly verbatim.

---

## 1. Principles (apply to every table and every migration)

1. **RLS on every tenant-scoped table, enforced, forced.** Every table carrying `tenant_id` gets `ENABLE ROW LEVEL SECURITY` **and** `FORCE ROW LEVEL SECURITY` (so even the table owner obeys policies - on Supabase the `postgres` role owns tables and would silently bypass RLS otherwise).
2. **Integer cents everywhere.** No `numeric`, no floats, no dollars columns. Every monetary column is `*_cents integer` (or `bigint` where sums could overflow - totals stay `integer`, fine at this scale). This is the schema half of the deterministic-pricing invariant.
3. **Domain-agnostic names only.** Columns describe generic concepts (items, rules, kinds, refs). If a column name only makes sense for one vertical, it is modeled wrong - push it into a `jsonb` config/attributes value.
4. **Denormalized `tenant_id` on `messages` and `tool_calls`.** The Architecture Doc's sketch had them keyed only through `conversation_id`/`message_id`; we carry `tenant_id` on both so RLS is direct, not join-dependent, and the leakage test can assert on them directly. (Flagged and approved in the planning phase.)
5. **Quotes are immutable once sent.** Only `status` may change after insert; line items and amounts never change retroactively. Enforced by trigger (section 6), not by convention.
6. **Text + CHECK instead of native enums.** Easier to evolve in migrations, equally safe.
7. **UUID primary keys** via `gen_random_uuid()`. Timestamps are `timestamptz`, default `now()`.

## 2. Roles and tenant context

### 2.1 Connection roles

| Role | Used by | Properties |
|---|---|---|
| `postgres` (Supabase-managed) | migrations only | table owner; FORCE RLS still applies to it |
| `wren_app` | the FastAPI backend (its only DB identity) | `LOGIN`, no `BYPASSRLS`, granted CRUD on app tables |
| `wren_resolver` | owns `resolve_tenant_slug` only | `NOLOGIN`, `BYPASSRLS` - the single, audited RLS bypass in the system (section 2.4) |

```sql
-- 0002_roles.sql. The migration runner substitutes ${WREN_APP_DB_PASSWORD} from env
-- before executing (plain-text placeholder substitution; this file is the only one
-- that needs it) - psql-style :'var' interpolation is NOT available in the runner.
create role wren_app login password '${WREN_APP_DB_PASSWORD}';
grant usage on schema public to wren_app;
-- per-table grants are in each table's migration; default privileges:
alter default privileges in schema public
  grant select, insert, update, delete on tables to wren_app;

create role wren_resolver nologin bypassrls;
```

### 2.2 Tenant context (the RLS key)

The backend sets two transaction-local settings before any query runs (FastAPI middleware, ticket T-004):

```sql
select set_config('app.tenant_id', :tenant_id, true);      -- '' when none resolved
select set_config('app.role',      :role,      true);      -- 'customer' | 'tenant_admin' | 'platform_admin' | 'service'
```

`'service'` is the backend acting on its own behalf in exactly one flow: the signup transaction (T-004). Its powers are defined by the Shape C policies below and nothing else - it is not a general-purpose superrole.

Helper functions every policy uses:

```sql
create or replace function app_tenant_id() returns uuid
  language sql stable as
$$ select nullif(current_setting('app.tenant_id', true), '')::uuid $$;

create or replace function app_is_platform_admin() returns boolean
  language sql stable as
$$ select current_setting('app.role', true) = 'platform_admin' $$;

create or replace function app_is_service() returns boolean
  language sql stable as
$$ select current_setting('app.role', true) = 'service' $$;
```

### 2.3 The three standard policy shapes

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

Platform-admin access is **read-only through policies** plus explicit writes on `tenants`/`platform_admins` only - the owner surface never edits tenant data rows. Every platform-admin query path in the backend is audited (logged with actor + query intent).

```sql
-- Shape B: platform-global table (no tenant_id): platform_admins, tenants (special-cased below)

-- Shape C: the service role (signup transaction only). Applied to exactly three
-- tables - tenants, tenant_config, users - and only for INSERT:
create policy service_signup_insert on <t>
  for insert
  with check (app_is_service());
```

The signup endpoint (T-004) runs its one transaction with `app.role = 'service'` and logs it as an audited service action; no other code path may set that role.

**Rule for the leakage test (T-022):** with `app.tenant_id` set to tenant A, every query against every tenant-scoped table must return zero tenant-B rows - including through joins, retrieval, and tool paths.

## 3. Schema - tenancy & identity

```sql
-- tenants: the platform-global registry. Customers/admins resolve INTO a tenant;
-- the row itself is readable by its own tenant and platform admins.
create table tenants (
  id          uuid primary key default gen_random_uuid(),
  slug        text not null unique check (slug ~ '^[a-z0-9](-?[a-z0-9])*$' and length(slug) between 3 and 40),
  name        text not null,
  status      text not null default 'active' check (status in ('provisioning', 'active', 'suspended')),
  created_at  timestamptz not null default now()
);
alter table tenants enable row level security;
alter table tenants force row level security;
create policy tenant_self_read   on tenants for select using (id = app_tenant_id());
create policy platform_admin_all on tenants for all
  using (app_is_platform_admin()) with check (app_is_platform_admin());
create policy service_signup_insert on tenants for insert with check (app_is_service());
-- slug -> tenant_id resolution (T-005): the unauthenticated customer surface must
-- resolve a slug BEFORE any tenant context exists, and FORCE RLS binds even the
-- table owner - so the resolver function is owned by wren_resolver (NOLOGIN,
-- BYPASSRLS; section 2.1), the single audited RLS bypass in the system. It is
-- SECURITY DEFINER, takes only a slug, and returns only the public columns below
-- (including brand, which the customer shell needs before any auth):
create or replace function resolve_tenant_slug(p_slug text)
  returns table (id uuid, name text, status text, brand jsonb)
  language sql stable security definer set search_path = public as
$$ select t.id, t.name, t.status, coalesce(c.brand, '{}'::jsonb)
     from tenants t left join tenant_config c on c.tenant_id = t.id
    where t.slug = p_slug $$;
alter function resolve_tenant_slug(text) owner to wren_resolver;
revoke all on function resolve_tenant_slug(text) from public;
grant execute on function resolve_tenant_slug(text) to wren_app;
-- The leakage test must include fishing attempts through this function (it is the
-- one path that crosses RLS): assert it never returns anything beyond these four
-- columns for the requested slug.

create table tenant_config (
  tenant_id             uuid primary key references tenants(id) on delete cascade,
  system_prompt         text not null default '',
  tone                  text not null default 'friendly',
  enabled_tools         jsonb not null default '["search_knowledge","recommend_items","lookup_order_or_ticket","get_quote_inputs","create_escalation"]',
  escalation_threshold  real not null default 0.5 check (escalation_threshold between 0 and 1),
  brand                 jsonb not null default '{}',   -- see frontend.md section 5: {"accent":"#RRGGBB","logo_url":...,"display_name":...}
  config                jsonb not null default '{}',   -- everything else: tax {"rate_bps":int,"label":text}, hours, locale...
  updated_at            timestamptz not null default now()
);
-- Shape A policies, using tenant_id column, plus Shape C (service_signup_insert).
-- Anonymous customers never read this table directly; the brand value they need
-- pre-auth arrives via resolve_tenant_slug above.

create table users (
  id          uuid primary key,                        -- = Supabase auth.users.id
  tenant_id   uuid not null references tenants(id) on delete cascade,
  role        text not null default 'owner' check (role in ('owner', 'staff')),
  created_at  timestamptz not null default now()
);
-- Shape A policies, plus Shape C (service_signup_insert).

create table platform_admins (
  user_id     uuid primary key,                        -- = Supabase auth.users.id
  created_at  timestamptz not null default now()
);
alter table platform_admins enable row level security;
alter table platform_admins force row level security;
create policy platform_admin_only on platform_admins for all
  using (app_is_platform_admin()) with check (app_is_platform_admin());
-- Bootstrap note: the first platform_admins row is inserted by migration/seed as postgres... 
-- which FORCE RLS would block; seeds for this table run with `set_config('app.role','platform_admin',true)`.
```

Indexes: `tenants(slug)` is covered by the unique constraint; `users(tenant_id)`.

## 4. Schema - knowledge & retrieval

```sql
create extension if not exists vector;

create table documents (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null references tenants(id) on delete cascade,
  filename     text not null,
  doc_type     text not null check (doc_type in ('policy', 'faq', 'catalog', 'price_list', 'other')),
  status       text not null default 'pending' check (status in ('pending', 'processing', 'ready', 'failed')),
  error        text,
  uploaded_at  timestamptz not null default now()
);
create index documents_tenant_idx on documents (tenant_id, status);

create table knowledge_chunks (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null references tenants(id) on delete cascade,
  document_id  uuid not null references documents(id) on delete cascade,
  content      text not null,
  embedding    vector(1536),                            -- text-embedding-3-small
  metadata     jsonb not null default '{}',             -- {"source":filename,"chunk_index":n,"kind":"prose"|"catalog_item"...}
  tsv          tsvector generated always as (to_tsvector('english', content)) stored,
  created_at   timestamptz not null default now()
);
create index knowledge_chunks_tenant_idx    on knowledge_chunks (tenant_id, document_id);
create index knowledge_chunks_embedding_idx on knowledge_chunks using hnsw (embedding vector_cosine_ops);
create index knowledge_chunks_tsv_idx       on knowledge_chunks using gin (tsv);
```

Both tables get Shape A policies. **Every retrieval query must still carry `where tenant_id = :tenant_id` explicitly** - RLS is the net, not the filter; the explicit predicate is what lets the planner combine the HNSW/GIN indexes with tenant scoping efficiently, and belt-and-braces is the point of M14.

Dense query shape (T-009): `order by embedding <=> :query_embedding limit :n`. Sparse: `where tsv @@ websearch_to_tsquery('english', :query) order by ts_rank(tsv, ...) desc limit :n`. Fuse with RRF in Python, then cross-encoder rerank.

## 5. Schema - catalog & pricing (the deterministic-pricing tables)

```sql
create table catalog_items (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null references tenants(id) on delete cascade,
  name         text not null,
  description  text not null default '',
  attributes   jsonb not null default '{}',             -- generic: {"category":..., "tags":[...], any per-tenant keys}
  price_cents  integer check (price_cents is null or price_cents >= 0),  -- null = not directly purchasable (e.g. a service described by rules)
  active       boolean not null default true,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
create index catalog_items_tenant_idx on catalog_items (tenant_id, active);

create table pricing_rules (
  id                 uuid primary key default gen_random_uuid(),
  tenant_id          uuid not null references tenants(id) on delete cascade,
  code               text not null,                     -- stable selector the agent emits, e.g. 'screen-repair-tier-a'
  label              text not null,
  unit_amount_cents  integer not null check (unit_amount_cents >= 0),
  unit               text not null default 'each',      -- 'each' | 'hour' | 'session' | free text, display-only
  conditions         jsonb not null default '{}',       -- {"min_qty":..,"applies_to":..} - engine-interpreted, generic keys only
  active             boolean not null default true,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now(),
  unique (tenant_id, code)
);
create index pricing_rules_tenant_idx on pricing_rules (tenant_id, active);

create table quotes (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null references tenants(id) on delete cascade,
  conversation_id  uuid not null,
  -- composite FK (same tenant-drift protection as messages; see section 6)
  foreign key (tenant_id, conversation_id) references conversations (tenant_id, id) on delete cascade,
  line_items       jsonb not null,     -- engine output verbatim: [{"kind":"rule"|"item","code"|"item_id":..,"label":..,"quantity":n,"unit_amount_cents":n,"line_total_cents":n}]
  subtotal_cents   integer not null check (subtotal_cents >= 0),
  tax_cents        integer not null default 0 check (tax_cents >= 0),
  total_cents      integer not null check (total_cents = subtotal_cents + tax_cents),
  status           text not null default 'draft' check (status in ('draft', 'sent', 'expired')),
  created_at       timestamptz not null default now()
);
create index quotes_tenant_idx on quotes (tenant_id, conversation_id);
```

All Shape A. **Only the pricing engine writes `quotes`** (application-layer rule, ticket T-017): the engine computes `line_items/subtotal/tax/total`; no other code path constructs those values. Immutability trigger in section 6 makes sent quotes tamper-proof.

## 6. Schema - conversations & operations

```sql
create table conversations (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references tenants(id) on delete cascade,
  customer_ref  text,                                   -- anonymous session id or customer-provided handle; no auth at core scope
  channel       text not null default 'web' check (channel in ('web')),  -- phase 2 adds more
  status        text not null default 'open' check (status in ('open', 'escalated', 'closed')),
  created_at    timestamptz not null default now(),
  unique (tenant_id, id)     -- composite-FK target: children prove they belong to the same tenant
);
create index conversations_tenant_idx on conversations (tenant_id, status, created_at desc);

-- Denormalized tenant_id (principle 4) is only safe if it cannot drift from the
-- parent row's tenant: FK checks bypass RLS, so without this a buggy insert under
-- tenant A's context could attach a message to tenant B's conversation and make it
-- visible to A. The composite FKs below make that impossible at the schema level.
create table messages (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null references tenants(id) on delete cascade,
  conversation_id  uuid not null,
  foreign key (tenant_id, conversation_id) references conversations (tenant_id, id) on delete cascade,
  unique (tenant_id, id),
  role             text not null check (role in ('customer', 'assistant', 'system', 'human_agent')),
  content          text not null,
  agent_node       text,                                -- which graph node authored it: 'supervisor','knowledge','quoting',...
  created_at       timestamptz not null default now()
);
create index messages_conversation_idx on messages (conversation_id, created_at);
create index messages_tenant_idx       on messages (tenant_id);

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
create index tool_calls_message_idx on tool_calls (message_id);
create index tool_calls_tenant_idx  on tool_calls (tenant_id, tool_name);

-- orders: mock order/ticket data, seeded per tenant. Generic on purpose - a phone shop's
-- repair ticket and a store's order are both "an order of some kind with a status".
create table orders (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references tenants(id) on delete cascade,
  ref_code      text not null,                          -- what a customer quotes back: 'R-1042', 'ORD-77'
  kind          text not null,                          -- tenant-defined: 'repair','order','booking',... data not code
  customer_ref  text,
  status        text not null,                          -- tenant-defined vocabulary, stored as data
  details       jsonb not null default '{}',            -- items, device, dates - whatever the tenant's world needs
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
create index escalations_tenant_idx on escalations (tenant_id, status, created_at desc);
```

All Shape A policies.

## 7. Schema - eval & cost

```sql
create table eval_cases (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references tenants(id) on delete cascade,
  case_type   text not null check (case_type in ('retrieval', 'generation', 'trajectory', 'injection', 'leakage')),
  input       jsonb not null,          -- e.g. {"query":...} or {"messages":[...],"persona":...}
  expected    jsonb not null,          -- e.g. {"relevant_chunk_ids":[...]} or {"tools":[...],"must_not_contain":[...]}
  created_at  timestamptz not null default now()
);

create table eval_runs (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references tenants(id) on delete cascade,
  run_type    text not null check (run_type in ('retrieval', 'generation', 'trajectory', 'injection', 'leakage', 'full')),
  metrics     jsonb not null,          -- {"recall_at_5":0.87,"mrr":...} - scorer-defined keys
  git_sha     text not null default '',
  created_at  timestamptz not null default now()
);
create index eval_runs_tenant_idx on eval_runs (tenant_id, run_type, created_at desc);

create table cost_logs (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null references tenants(id) on delete cascade,
  conversation_id  uuid references conversations(id) on delete set null,
  model            text not null,
  input_tokens     integer not null default 0,
  output_tokens    integer not null default 0,
  cost_usd         numeric(12,6) not null default 0,   -- the one non-cents money column: observability metadata, never customer-facing pricing
  created_at       timestamptz not null default now()
);
create index cost_logs_tenant_idx on cost_logs (tenant_id, created_at desc);
create index cost_logs_conversation_idx on cost_logs (conversation_id);
```

All Shape A policies.

## 8. Triggers

```sql
-- updated_at maintenance (tenant_config, catalog_items, pricing_rules, orders)
create or replace function touch_updated_at() returns trigger language plpgsql as
$$ begin new.updated_at = now(); return new; end $$;
create trigger <t>_touch before update on <t> for each row execute function touch_updated_at();

-- quote immutability: after insert, only draft->sent->expired status transitions are allowed
create or replace function quotes_immutable() returns trigger language plpgsql as
$$
begin
  if new.line_items    is distinct from old.line_items
  or new.subtotal_cents is distinct from old.subtotal_cents
  or new.tax_cents      is distinct from old.tax_cents
  or new.total_cents    is distinct from old.total_cents
  or new.tenant_id      is distinct from old.tenant_id
  or new.conversation_id is distinct from old.conversation_id then
    raise exception 'quotes are immutable except status';
  end if;
  if not ((old.status, new.status) in (('draft','sent'), ('draft','expired'), ('sent','expired'), (old.status, old.status))) then
    raise exception 'invalid quote status transition % -> %', old.status, new.status;
  end if;
  return new;
end
$$;
create trigger quotes_immutable_trg before update on quotes for each row execute function quotes_immutable();
```

## 9. Migration order

One migration file per numbered step, `backend/migrations/NNNN_<name>.sql`, applied in order by a plain runner (T-002; a simple Python runner over `schema_migrations(version text primary key, applied_at timestamptz)` is fine - no heavy framework):

```
0001_extensions.sql        vector; helper functions app_tenant_id/app_is_platform_admin; touch_updated_at
0002_roles.sql             wren_app role + default privileges
0003_tenancy.sql           tenants, tenant_config, users, platform_admins (+ RLS, resolve_tenant_slug)
0004_knowledge.sql         documents, knowledge_chunks (+ RLS, HNSW/GIN indexes)
0005_conversations.sql     conversations, messages, tool_calls (+ RLS)   -- before quotes (FK target)
0006_commerce.sql          catalog_items, pricing_rules, quotes (+ RLS, quotes_immutable)
0007_operations.sql        orders, escalations (+ RLS)
0008_eval_cost.sql         eval_cases, eval_runs, cost_logs (+ RLS)
```

Every table migration ends with its `enable/force row level security` + policies + grants to `wren_app`. A table without RLS must never survive a migration file - the leakage test's schema audit (below) enforces this.

## 10. Seed plan

`backend/seeds/` (idempotent scripts, runnable per environment):

- `seed_tenant1_phoneshop.py` - Tenant 1 (anchor): slug `bytefix`, tenant_config (tone, escalation threshold, tax in `config`), ~15 catalog_items (phones, accessories, tiered repair services), ~12 pricing_rules (screen repair tiers by device class, battery swap, diagnostics fee...), ~20 mock orders (kind 'repair' and 'order', varied statuses), knowledge docs (policies, FAQ, price list) via the real ingestion pipeline.
- `seed_tenant2_dental.py` - Tenant 2 (generalization proof, T-037): created **only** through the conversational onboarding flow + uploads; this seed holds just the raw input documents and the interview script, never direct table writes. That is the point of the proof.
- `seed_leakage_pair.py` - two throwaway tenants with disjoint secret facts (e.g. unique nonsense strings embedded in each tenant's knowledge, catalog, orders) used by the leakage test T-022.
- `seed_platform_admin.py` - the founder's auth user id into `platform_admins`.

## 11. Schema audit (ships with T-003, runs in CI)

A test that queries `pg_tables`/`pg_policies` and asserts: every table with a `tenant_id` column has RLS enabled **and forced** and at least the `tenant_isolation` policy; every monetary column matches `%_cents` and is integer-typed (`cost_logs.cost_usd` is the single allowed exception). This turns principles 1-2 from prose into a failing test.

*End of database design. The pricing engine's computation contract lives with its ticket (T-016); the schema above is everything it reads and writes.*
