-- 0007_operations.sql - orders, escalations (+ RLS). Generic, domain-agnostic shapes.

create table orders (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references tenants(id) on delete cascade,
  ref_code      text not null,
  kind          text not null,           -- tenant-defined vocabulary, stored as data
  customer_ref  text,
  status        text not null,           -- tenant-defined vocabulary, stored as data
  details       jsonb not null default '{}',
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  unique (tenant_id, ref_code)
);
create index orders_tenant_idx on orders (tenant_id, status);
alter table orders enable row level security;
alter table orders force row level security;
create policy tenant_isolation    on orders for all
  using (tenant_id = app_tenant_id()) with check (tenant_id = app_tenant_id());
create policy platform_admin_read on orders for select using (app_is_platform_admin());
create trigger orders_touch before update on orders
  for each row execute function touch_updated_at();
grant select, insert, update, delete on orders to wren_app;

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
alter table escalations enable row level security;
alter table escalations force row level security;
create policy tenant_isolation    on escalations for all
  using (tenant_id = app_tenant_id()) with check (tenant_id = app_tenant_id());
create policy platform_admin_read on escalations for select using (app_is_platform_admin());
grant select, insert, update, delete on escalations to wren_app;
