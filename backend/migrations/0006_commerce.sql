-- 0006_commerce.sql - catalog_items, pricing_rules, quotes (+ RLS, immutability).
-- The schema half of deterministic pricing: every money column is integer *_cents.

create table catalog_items (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null references tenants(id) on delete cascade,
  name         text not null,
  description  text not null default '',
  attributes   jsonb not null default '{}',
  price_cents  integer check (price_cents is null or price_cents >= 0),
  active       boolean not null default true,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
create index catalog_items_tenant_idx on catalog_items (tenant_id, active);
alter table catalog_items enable row level security;
alter table catalog_items force row level security;
create policy tenant_isolation    on catalog_items for all
  using (tenant_id = app_tenant_id()) with check (tenant_id = app_tenant_id());
create policy platform_admin_read on catalog_items for select using (app_is_platform_admin());
create trigger catalog_items_touch before update on catalog_items
  for each row execute function touch_updated_at();
grant select, insert, update, delete on catalog_items to wren_app;

create table pricing_rules (
  id                 uuid primary key default gen_random_uuid(),
  tenant_id          uuid not null references tenants(id) on delete cascade,
  code               text not null,
  label              text not null,
  unit_amount_cents  integer not null check (unit_amount_cents >= 0),
  unit               text not null default 'each',
  conditions         jsonb not null default '{}',
  active             boolean not null default true,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now(),
  unique (tenant_id, code)
);
create index pricing_rules_tenant_idx on pricing_rules (tenant_id, active);
alter table pricing_rules enable row level security;
alter table pricing_rules force row level security;
create policy tenant_isolation    on pricing_rules for all
  using (tenant_id = app_tenant_id()) with check (tenant_id = app_tenant_id());
create policy platform_admin_read on pricing_rules for select using (app_is_platform_admin());
create trigger pricing_rules_touch before update on pricing_rules
  for each row execute function touch_updated_at();
grant select, insert, update, delete on pricing_rules to wren_app;

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
create index quotes_tenant_idx on quotes (tenant_id, conversation_id);
alter table quotes enable row level security;
alter table quotes force row level security;
create policy tenant_isolation    on quotes for all
  using (tenant_id = app_tenant_id()) with check (tenant_id = app_tenant_id());
create policy platform_admin_read on quotes for select using (app_is_platform_admin());
-- No DELETE for the app role: quotes are tamper-proof records (principle 5). Tenant
-- offboarding still works - FK cascades run as the table owner, not wren_app.
grant select, insert, update on quotes to wren_app;
revoke delete on quotes from wren_app;   -- undo the 0002 default privilege

-- Quotes are immutable once created; only draft->sent->expired status may change.
-- id/created_at are guarded too (with the DELETE revoke above, principle 5 of
-- database.md taken literally - slightly stronger than the doc's sample trigger;
-- recorded in .agents/memory.md).
create or replace function quotes_immutable() returns trigger language plpgsql as
$$
begin
  if new.line_items      is distinct from old.line_items
  or new.subtotal_cents  is distinct from old.subtotal_cents
  or new.tax_cents       is distinct from old.tax_cents
  or new.total_cents     is distinct from old.total_cents
  or new.tenant_id       is distinct from old.tenant_id
  or new.conversation_id is distinct from old.conversation_id
  or new.id              is distinct from old.id
  or new.created_at      is distinct from old.created_at then
    raise exception 'quotes are immutable except status';
  end if;
  if not ((old.status, new.status) in (('draft','sent'), ('draft','expired'), ('sent','expired'), (old.status, old.status))) then
    raise exception 'invalid quote status transition % -> %', old.status, new.status;
  end if;
  return new;
end
$$;
create trigger quotes_immutable_trg before update on quotes
  for each row execute function quotes_immutable();
