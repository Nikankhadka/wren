# Phase 14: schema drop (W)

One ticket, and it exists only to finish something W-9 deliberately left
half-done. W-9 stopped every application code path from reading
`tenant_config.system_prompt` and `.tone`, backfilled the structured
`config->customer_voice` that replaced them, and stopped there: the columns and
their seed writes are still in place. Dropping them is destructive and cannot
share a squash-merge with the code that stops depending on them, because a
single commit cannot be both "deploy forward-compatible code" and "run the
destructive migration after it is verified in production".

The `W-` prefix continues from [Phase 13](13-walkthrough.md) rather than opening
a new one: this ticket has no independent product goal, and reading it without
W-9's record beside it would not make sense.

---

## W-10: drop the retired tenant prompt columns

### Summary

Drop `tenant_config.system_prompt` and `tenant_config.tone` and remove the last
code that writes them. The columns have no reader in `backend/app` after W-9;
this ticket removes the writers, drops the columns in migration `0028`, and
reconciles the schema documentation that still describes them as live.

### Why

Two columns that nothing reads are not harmless. `system_prompt` is free tenant
prose that used to be interpolated straight into a customer-facing prompt, so
for as long as the column exists someone can reasonably assume it still is, and
a future change can quietly re-point a prompt at it. `tone` is the same shape at
smaller stakes. W-9 replaced both with a bounded, structured value
(`config->customer_voice`) precisely so that free prose could not reach the
model as authority; leaving the old columns writable leaves the old path one
line of code away from returning.

The follow-up also has a cost of its own if it is skipped. `seeds/_helpers.py`
still computes and inserts a `system_prompt` for every seeded tenant, and
`seed_injection_probe.py` still writes one that carries the leak marker, so a
reader of the seeds cannot tell which of the two marker copies the injection
eval actually scores.

Same shape as
[`0025_schema_cleanup.sql:33`](../../../../backend/migrations/0025_schema_cleanup.sql#L33),
which dropped `tenant_config.escalation_threshold` after the code that read it
had already gone.

### Scope

This ticket drops two columns and deletes their writers. It changes no runtime
behavior a customer or an owner can observe, adds no feature, and touches no
prompt text. If any part of it turns out to change behavior, that is a defect in
W-9's claim that nothing reads these columns, and it stops this ticket rather
than being worked around inside it.

### Preconditions

Do not start until all three hold:

1. W-9 is deployed to production and a customer turn has been served from the
   deployed build.
2. `select count(*) from tenant_config where not (config ? 'customer_voice')`
   returns 0 against the production database, so migration `0027`'s backfill
   reached every row.
3. A production database backup exists and its restore path is known. A column
   drop is not reversible by re-running a migration.

### Technical spec

**Writers to delete.** Each of these is a write with no reader:

- `system_prompt_for`
  ([flow.py:61](../../../../backend/app/onboarding/flow.py#L61)) - the only
  producer of the string. Delete the function.
- [`controller.py:545`](../../../../backend/app/features/onboarding/controller.py#L545)
  computes it on confirm and passes it down. Delete the call and the argument.
- `apply_confirmation`'s `system_prompt` parameter and the `set system_prompt=$2`
  clause in its update
  ([service.py:58,84-93](../../../../backend/app/features/onboarding/service.py#L58)).
  The `config->profile` and `config->customer_voice` writes in the same
  statement stay exactly as they are, in the same transaction.
- `seeds/_helpers.py`'s `system_prompt` and `tone` parameters and both insert
  statements that name those columns.
- `seed_injection_probe.py`'s `SYSTEM_PROMPT` constant. `LEAK_MARKER` stays
  imported from
  [`app/agents/contract.py`](../../../../backend/app/agents/contract.py), which is
  where the copy the injection eval scores has lived since W-9.

**Migration `0028_drop_tenant_prompt_columns.sql`.** Two statements, no
backfill, no data movement:

```sql
alter table tenant_config drop column system_prompt;
alter table tenant_config drop column tone;
```

The columns are `not null default ''` and `not null default 'friendly'`, so no
constraint, index, or policy references them and the drop needs no companion
change.

**Documentation.** `docs/agencx/design/database.md` still shows both columns in
the `tenant_config` DDL and its migration list must gain `0028`.
`test_migrations.py`'s count and its narrated migration list both move from 27
to 28.

### Tests

- `test_migrations.py`: the count is 28, `0028` is narrated, and a re-run is
  still idempotent.
- `test_schema_audit.py` stays green: no policy, grant, or RLS assertion names
  either column.
- Onboarding confirm writes `config->profile` and `config->customer_voice` in
  one transaction and completes without the dropped column, asserted through the
  existing confirm test rather than a new one.
- Every seed runs against a migrated database:
  `seed_demo`, `seed_tenant1_phoneshop`, `seed_leakage_pair`, and
  `seed_injection_probe`.
- `make check` and `make eval-skip-llm` green. `make eval` green with a
  configured provider, which is what proves the eight `injection_set.jsonl`
  prompt-leak cases still score a marker that reaches a real prompt.

### Definition of done

- [ ] No code in `backend/` writes `tenant_config.system_prompt` or
      `tenant_config.tone`; `system_prompt_for` is deleted, not left unused.
- [ ] Migration `0028` drops both columns and applies cleanly to a database
      already carrying `0001` through `0027`.
- [ ] Every seed runs green against the migrated schema, and
      `seed_injection_probe.py` plants the leak marker only through the contract.
- [ ] `database.md`'s `tenant_config` DDL and migration list match the shipped
      schema.
- [ ] `make check`, `make eval-skip-llm`, and `make eval` are green, with
      `make eval`'s injection pass rate showing no drop against its baseline.
- [ ] The three preconditions above were checked and their results recorded in
      `progress.md`.
