-- 0003_tenancy.sql - tenants, tenant_config, users, platform_admins (+ RLS, resolver).

-- tenants: platform-global registry. Special-cased policies (no tenant_id column).
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
grant select, insert, update, delete on tenants to wren_app;

create table tenant_config (
  tenant_id             uuid primary key references tenants(id) on delete cascade,
  system_prompt         text not null default '',
  tone                  text not null default 'friendly',
  enabled_tools         jsonb not null default '["search_knowledge","recommend_items","lookup_order_or_ticket","get_quote_inputs","create_escalation"]',
  escalation_threshold  real not null default 0.5 check (escalation_threshold between 0 and 1),
  brand                 jsonb not null default '{}',
  config                jsonb not null default '{}',
  updated_at            timestamptz not null default now()
);
alter table tenant_config enable row level security;
alter table tenant_config force row level security;
create policy tenant_isolation      on tenant_config for all
  using (tenant_id = app_tenant_id()) with check (tenant_id = app_tenant_id());
create policy platform_admin_read   on tenant_config for select using (app_is_platform_admin());
create policy service_signup_insert on tenant_config for insert with check (app_is_service());
create trigger tenant_config_touch before update on tenant_config
  for each row execute function touch_updated_at();
grant select, insert, update, delete on tenant_config to wren_app;

create table users (
  id          uuid primary key,               -- = Supabase auth.users.id
  tenant_id   uuid not null references tenants(id) on delete cascade,
  role        text not null default 'owner' check (role in ('owner', 'staff')),
  created_at  timestamptz not null default now()
);
create index users_tenant_idx on users (tenant_id);
alter table users enable row level security;
alter table users force row level security;
create policy tenant_isolation      on users for all
  using (tenant_id = app_tenant_id()) with check (tenant_id = app_tenant_id());
create policy platform_admin_read   on users for select using (app_is_platform_admin());
create policy service_signup_insert on users for insert with check (app_is_service());
grant select, insert, update, delete on users to wren_app;

create table platform_admins (
  user_id     uuid primary key,               -- = Supabase auth.users.id
  created_at  timestamptz not null default now()
);
alter table platform_admins enable row level security;
alter table platform_admins force row level security;
create policy platform_admin_only on platform_admins for all
  using (app_is_platform_admin()) with check (app_is_platform_admin());
grant select, insert, update, delete on platform_admins to wren_app;

-- Slug -> tenant resolution. Must be defined AFTER tenant_config exists because the
-- SQL body references it. Owned by wren_resolver (BYPASSRLS) and SECURITY DEFINER so
-- the unauthenticated customer surface can resolve a slug before any tenant context.
create or replace function resolve_tenant_slug(p_slug text)
  returns table (id uuid, name text, status text, brand jsonb)
  language sql stable security definer set search_path = public as
$$ select t.id, t.name, t.status, coalesce(c.brand, '{}'::jsonb)
     from tenants t left join tenant_config c on c.tenant_id = t.id
    where t.slug = p_slug $$;
alter function resolve_tenant_slug(text) owner to wren_resolver;
grant select on tenants, tenant_config to wren_resolver;
revoke all on function resolve_tenant_slug(text) from public;
grant execute on function resolve_tenant_slug(text) to wren_app;
