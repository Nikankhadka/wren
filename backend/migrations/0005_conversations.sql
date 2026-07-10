-- 0005_conversations.sql - conversations, messages, tool_calls (+ RLS).
-- Before commerce because quotes' composite FK targets conversations.

create table conversations (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references tenants(id) on delete cascade,
  customer_ref  text,
  channel       text not null default 'web' check (channel in ('web')),
  status        text not null default 'open' check (status in ('open', 'escalated', 'closed')),
  created_at    timestamptz not null default now(),
  unique (tenant_id, id)     -- composite-FK target: children prove same tenant
);
create index conversations_tenant_idx on conversations (tenant_id, status, created_at desc);
alter table conversations enable row level security;
alter table conversations force row level security;
create policy tenant_isolation    on conversations for all
  using (tenant_id = app_tenant_id()) with check (tenant_id = app_tenant_id());
create policy platform_admin_read on conversations for select using (app_is_platform_admin());
grant select, insert, update, delete on conversations to wren_app;

-- Denormalized tenant_id is safe only because the composite FK forbids it drifting
-- from the parent conversation's tenant (FK checks bypass RLS otherwise).
create table messages (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null references tenants(id) on delete cascade,
  conversation_id  uuid not null,
  foreign key (tenant_id, conversation_id) references conversations (tenant_id, id) on delete cascade,
  unique (tenant_id, id),
  role             text not null check (role in ('customer', 'assistant', 'system', 'human_agent')),
  content          text not null,
  agent_node       text,
  created_at       timestamptz not null default now()
);
create index messages_conversation_idx on messages (conversation_id, created_at);
create index messages_tenant_idx       on messages (tenant_id);
alter table messages enable row level security;
alter table messages force row level security;
create policy tenant_isolation    on messages for all
  using (tenant_id = app_tenant_id()) with check (tenant_id = app_tenant_id());
create policy platform_admin_read on messages for select using (app_is_platform_admin());
grant select, insert, update, delete on messages to wren_app;

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
alter table tool_calls enable row level security;
alter table tool_calls force row level security;
create policy tenant_isolation    on tool_calls for all
  using (tenant_id = app_tenant_id()) with check (tenant_id = app_tenant_id());
create policy platform_admin_read on tool_calls for select using (app_is_platform_admin());
grant select, insert, update, delete on tool_calls to wren_app;
