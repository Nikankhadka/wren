-- 0001_extensions.sql - pgvector + the helper functions every RLS policy uses.

create extension if not exists vector;

-- Tenant-context accessors (see database.md section 2.2). All read the two
-- transaction-local settings the backend sets before any query.
create or replace function app_tenant_id() returns uuid
  language sql stable as
$$ select nullif(current_setting('app.tenant_id', true), '')::uuid $$;

create or replace function app_is_platform_admin() returns boolean
  language sql stable as
$$ select current_setting('app.role', true) = 'platform_admin' $$;

create or replace function app_is_service() returns boolean
  language sql stable as
$$ select current_setting('app.role', true) = 'service' $$;

-- updated_at maintenance, reused by several tables (database.md section 8).
create or replace function touch_updated_at() returns trigger language plpgsql as
$$ begin new.updated_at = now(); return new; end $$;
