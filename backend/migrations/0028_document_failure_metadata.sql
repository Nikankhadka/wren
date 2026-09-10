-- 0028_document_failure_metadata.sql - W-11: keep a processing failure instead
-- of discarding it, with enough shape for an owner to retry it.
--
-- draft_from_upload used to raise a 422 on any structuring or extraction
-- failure and store nothing, on the theory that the owner was standing at the
-- screen waiting for a result. W-11 reverses that half: once a file has
-- passed validation (_reject_upload, unchanged) and is on disk, a failure
-- during processing is now kept as a 'failed' draft so retry-draft has
-- something to retry. Validation rejections still store nothing - only the
-- accepted-then-failed case changes.
--
-- Three typed columns rather than a key inside `offerings` (0026): a
-- processing failure is a fact about the document itself, not about the
-- offerings extracted from it, and a structuring or embedding failure has
-- nothing to do with offerings at all. `error` (0004) already carries the
-- customer-safe message; these three carry what it doesn't:
--
-- - failure_stage: which step failed - 'structure', 'extract', or 'embed'.
--   Structuring and extraction are draft_from_upload's and retry-draft's own
--   passes; embed is process_document's chunk+embed pass, used by the older
--   direct-publish upload, reprocess, and save/publish. All three already
--   land on status = 'failed'; this says which one.
-- - failure_retryable: every failure this ticket stores comes from re-running
--   the same pipeline against the same stored input, so retrying is always
--   sane - the column exists so a future permanently-unretryable case has
--   somewhere to say so without a schema change.
-- - failed_at: when the failure happened, for support and ops.
--
-- All three stay null except on a 'failed' row, the same policy 0019 and 0026
-- use for `structured` and `offerings` being null before a document reaches
-- that pass.
--
-- No RLS or grant statement is needed: both are table-level and adding a
-- column changes neither.
alter table documents add column failure_stage text
  check (failure_stage in ('structure', 'extract', 'embed'));
alter table documents add column failure_retryable boolean;
alter table documents add column failed_at timestamptz;
