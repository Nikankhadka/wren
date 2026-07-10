-- 0008_eval_cost.sql - eval_cases, eval_runs, cost_logs (+ RLS).

create table eval_cases (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references tenants(id) on delete cascade,
  case_type   text not null check (case_type in ('retrieval', 'generation', 'trajectory', 'injection', 'leakage')),
  input       jsonb not null,
  expected    jsonb not null,
  created_at  timestamptz not null default now()
);
create index eval_cases_tenant_idx on eval_cases (tenant_id, case_type);
alter table eval_cases enable row level security;
alter table eval_cases force row level security;
create policy tenant_isolation    on eval_cases for all
  using (tenant_id = app_tenant_id()) with check (tenant_id = app_tenant_id());
create policy platform_admin_read on eval_cases for select using (app_is_platform_admin());
grant select, insert, update, delete on eval_cases to wren_app;

create table eval_runs (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references tenants(id) on delete cascade,
  run_type    text not null check (run_type in ('retrieval', 'generation', 'trajectory', 'injection', 'leakage', 'full')),
  metrics     jsonb not null,
  git_sha     text not null default '',
  created_at  timestamptz not null default now()
);
create index eval_runs_tenant_idx on eval_runs (tenant_id, run_type, created_at desc);
alter table eval_runs enable row level security;
alter table eval_runs force row level security;
create policy tenant_isolation    on eval_runs for all
  using (tenant_id = app_tenant_id()) with check (tenant_id = app_tenant_id());
create policy platform_admin_read on eval_runs for select using (app_is_platform_admin());
grant select, insert, update, delete on eval_runs to wren_app;

create table cost_logs (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null references tenants(id) on delete cascade,
  conversation_id  uuid references conversations(id) on delete set null,
  model            text not null,
  input_tokens     integer not null default 0,
  output_tokens    integer not null default 0,
  cost_usd         numeric(12,6) not null default 0,   -- the one non-cents money column: observability only
  created_at       timestamptz not null default now()
);
create index cost_logs_tenant_idx on cost_logs (tenant_id, created_at desc);
create index cost_logs_conversation_idx on cost_logs (conversation_id);
alter table cost_logs enable row level security;
alter table cost_logs force row level security;
create policy tenant_isolation    on cost_logs for all
  using (tenant_id = app_tenant_id()) with check (tenant_id = app_tenant_id());
create policy platform_admin_read on cost_logs for select using (app_is_platform_admin());
grant select, insert, update, delete on cost_logs to wren_app;
