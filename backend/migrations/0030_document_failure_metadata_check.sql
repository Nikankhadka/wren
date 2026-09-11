-- 0030_document_failure_metadata_check.sql - keep failure metadata off rows
-- that are not failed, without requiring legacy failed rows to be backfilled.
-- 0028 is already merged and 0029 is reserved for W-10, so this append-only
-- constraint uses 0030 instead of mutating either migration.
alter table documents add constraint documents_failure_metadata_check
  check (
    status = 'failed'
    or (
      failure_stage is null
      and failure_retryable is null
      and failed_at is null
    )
  );
