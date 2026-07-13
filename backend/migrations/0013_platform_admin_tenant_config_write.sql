-- 0013_platform_admin_tenant_config_write.sql - T-033: platform admins can
-- provision a tenant_config row for a tenant they just created.
--
-- tenant_config only granted platform_admin SELECT (0003_tenancy.sql) - an
-- oversight for this exact need: provisioning a tenant from the platform
-- surface must create both the tenants row AND its tenant_config row in the
-- same transaction (tenant_config.tenant_id has no default, every tenant
-- needs exactly one row). platform_admin already has unconditional `for all`
-- on tenants itself (the same table this row belongs to) - widening
-- tenant_config to match is consistent with that existing authority, not a
-- new boundary. tenant_isolation (tenant-scoped) and service_signup_insert
-- (self-serve signup) are untouched.
drop policy platform_admin_read on tenant_config;
create policy platform_admin_all on tenant_config for all
  using (app_is_platform_admin()) with check (app_is_platform_admin());
