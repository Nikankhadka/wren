-- 0004_knowledge.sql - documents, knowledge_chunks (+ RLS, HNSW/GIN indexes).

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
alter table documents enable row level security;
alter table documents force row level security;
create policy tenant_isolation    on documents for all
  using (tenant_id = app_tenant_id()) with check (tenant_id = app_tenant_id());
create policy platform_admin_read on documents for select using (app_is_platform_admin());
grant select, insert, update, delete on documents to wren_app;

create table knowledge_chunks (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null references tenants(id) on delete cascade,
  document_id  uuid not null references documents(id) on delete cascade,
  content      text not null,
  embedding    vector(1536),                            -- text-embedding-3-small
  metadata     jsonb not null default '{}',
  tsv          tsvector generated always as (to_tsvector('english', content)) stored,
  created_at   timestamptz not null default now()
);
create index knowledge_chunks_tenant_idx    on knowledge_chunks (tenant_id, document_id);
create index knowledge_chunks_embedding_idx on knowledge_chunks using hnsw (embedding vector_cosine_ops);
create index knowledge_chunks_tsv_idx       on knowledge_chunks using gin (tsv);
alter table knowledge_chunks enable row level security;
alter table knowledge_chunks force row level security;
create policy tenant_isolation    on knowledge_chunks for all
  using (tenant_id = app_tenant_id()) with check (tenant_id = app_tenant_id());
create policy platform_admin_read on knowledge_chunks for select using (app_is_platform_admin());
grant select, insert, update, delete on knowledge_chunks to wren_app;
