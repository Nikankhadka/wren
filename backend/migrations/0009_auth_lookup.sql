-- 0009_auth_lookup.sql - pre-context user lookups for auth (T-004).
--
-- The tenant-admin and platform-admin auth dependencies must resolve a Supabase
-- user id to (tenant_id, role) / platform-admin membership BEFORE any tenant
-- context exists, so a normal RLS-scoped query cannot do it - the same
-- chicken-and-egg problem resolve_tenant_slug (0003) solves for slugs. These two
-- functions are owned by wren_resolver (NOLOGIN, BYPASSRLS; the single audited
-- RLS bypass in the system, database.md section 2.1), SECURITY DEFINER, and each
-- returns only the narrow shape auth.py needs - never a full row.

create or replace function resolve_user_tenant(p_user_id uuid)
  returns table (tenant_id uuid, role text)
  language sql stable security definer set search_path = public as
$$ select u.tenant_id, u.role from users u where u.id = p_user_id $$;
alter function resolve_user_tenant(uuid) owner to wren_resolver;
-- Column-level grant only: matches the function's two-column contract so a future
-- resolver-owned function cannot quietly widen the pre-context read surface.
grant select (id, tenant_id, role) on users to wren_resolver;
revoke all on function resolve_user_tenant(uuid) from public;
grant execute on function resolve_user_tenant(uuid) to wren_app;

create or replace function resolve_platform_admin(p_user_id uuid)
  returns boolean
  language sql stable security definer set search_path = public as
$$ select exists (select 1 from platform_admins p where p.user_id = p_user_id) $$;
alter function resolve_platform_admin(uuid) owner to wren_resolver;
grant select (user_id) on platform_admins to wren_resolver;
revoke all on function resolve_platform_admin(uuid) from public;
grant execute on function resolve_platform_admin(uuid) to wren_app;
