# Phase 15: document review and privacy workflow

This ticket follows W-9's customer-agent contract work. It gives onboarding
and Business > Knowledge one retained document-review workspace, reliable
multi-file processing, safe replacement and retry behavior, partial
publication, and a stable product disclosure for document storage and AI
processing. It keeps the existing extraction and storage boundaries and does
not introduce a legal Privacy Policy.

It ships as three tickets, each on its own branch, because they touch
different layers and unblock independently: W-11a is a backend contract with
no UI, W-11b is a one-file frontend bug fix with the highest value per line,
and W-11c is the batch-upload UI that depends on both. Definition-of-done
items below live under whichever ticket actually delivers them.

## Decisions

1. **The multi-file flow changes with per-file progress visible.** Today,
   files upload sequentially and the review sheet opens on the first accepted
   draft while later files still process. As of W-11c, every file settles
   first and one combined review opens, with a live Processing, Ready, or
   Failed row per file shown while the owner waits.
2. **A batch caps at five files, three processed concurrently.** A per-file
   timeout surfaces as a retryable Failed row and never fails the whole batch.
3. **The shipped `ReviewSheet` and thread components are the design
   reference.** `agencx-prototype-v6.html` has no document-review screen, so
   the three net-new W-11c surfaces match the structure, spacing, and tokens
   of what's already shipped rather than a prototype mockup.
4. **A processing failure on an accepted upload is now a stored, retryable
   draft.** It used to be a 422 with nothing stored. Validation rejections
   (unsupported type, oversize) are unchanged: still a 422, still nothing
   stored. This reversal is deliberate - see W-11a below.

## W-11a: backend contract

Branch `feat/w-11a-document-batch`. No UI; fully testable through API tests.
**Merged to `development` via PR #31.** Corrective follow-up merged via PR #34
(`fix/w-11a-backend-corrections`).

### User stories

- As an owner, a processing failure on a file I uploaded is kept as a
  retryable draft instead of vanishing behind a 422 - I can retry it without
  re-uploading.
- As an owner, when I replace a source document, offerings that only that
  document supported are dropped unless I'd edited them (kept and marked
  orphaned), offerings matched in the new document merge normally, and a
  price disagreement from the merge becomes a decision I have to make, not a
  silent overwrite.
- As an owner, publishing several reviewed documents at once never gets
  blocked by one bad document - the rest still publish, the bad one comes
  back as a clear failure I can act on, and my edits to it aren't lost.

### Technical spec

- Migration `0028_document_failure_metadata.sql` adds
  `documents.failure_stage` (`structure` | `extract` | `embed`),
  `failure_retryable`, and `failed_at`. `error` (0004) still carries the
  customer-safe message. Migration `0030_document_failure_metadata_check.sql`
  keeps those fields null on non-failed rows while allowing legacy failed rows
  with incomplete metadata.
- `draft_from_upload` stores an accepted-then-failed upload as `status =
  'failed'` instead of raising; `POST /api/knowledge/{document_id}/retry-draft`
  re-reads the stored file, re-runs structuring and extraction, and returns
  the document to `status = 'draft'` without publishing anything. An
  extraction that degrades to zero candidates (not an exception) is not a
  document failure - it lands as an ordinary draft with `extraction_status =
  'failed'`, matching what `extract_offerings` already documented.
- `PendingOffering` gained `supporting_document_ids` and `support_state`
  (`supported` | `orphaned`). `reconcile_replacement`, beside
  `merge_offerings` in `onboarding/flow.py`, is the set-level policy for which
  offerings survive a document replacement; `merge_offerings` itself stays the
  only pairwise precedence policy, now with one more caller.
- `PUT /api/onboarding/knowledge/batch`:
  - Request: one to five unique `documents: [{document_id, sections}]`,
    `offerings: [{offering, supporting_document_ids}]`, `accept_price_changes`.
  - Response: `published: [uuid]`, `failed: [{document_id, error}]`, and the
    actually-persisted `offering_candidates`.
  - Always 200 when auth and validation pass - partial failure is data, not a
    status code. A document that fails (not found, a price conflict, or a
    processing failure surfaced at publish time) never aborts the rest; its
    submitted sections are still saved so the edit isn't lost. An offering is
    withheld from the response only when every document it depends on hard-
    failed in this same batch - a price conflict never withholds the
    offering it names, since the owner needs it there to resubmit with
    `accept_price_changes`.
  - Only `draft` documents are reviewable batch targets. `ready`, `processing`,
    and `failed` rows return per-document failures without mutation. Storage
    boundary failures are isolated to that document and return a safe failure
    while later documents continue.
  - The existing single-document `PUT /api/onboarding/knowledge/{document_id}`
    is unchanged.

### Definition of done

- [x] A processing failure on an accepted upload is a stored, retryable draft;
      a validation rejection still stores nothing.
- [x] `retry-draft` reprocesses the stored file and never publishes.
- [x] Document replacement reconciliation (drop / keep-and-orphan / merge)
      matches the three rules above, including legacy owner-provenance edge
      cases.
- [x] `PUT /api/onboarding/knowledge/batch` publishes independently per
      document, is tenant-scoped, never auto-publishes a document it couldn't
      process, and a price conflict is recoverable rather than data loss.
- [x] Covered by API tests (`test_knowledge_api.py`,
      `test_onboarding_knowledge_batch.py`, `test_onboarding_agent.py`) and
      generated frontend types (`api-types.ts`).
- [x] `make check` green (994 backend + 120 frontend tests).
- [x] Reviewed (two Opus passes - the second caught and fixed a bug in the
      first fix pass's price-conflict withholding logic).

## W-11b: the retained workspace

Branch `fix/w-11b-retained-review`. Independent of W-11a; highest value per
line. **Merged to `development` via PR #32.**

### User story

- As an owner, closing the review sheet mid-edit and reopening it shows my
  edits exactly as I left them, instead of losing everything the sheet held.

### Technical spec

`ReviewSheet`'s props change from `record: KnowledgeRecord | null` to
`workspace: ReviewWorkspace | null` plus `open: boolean`. The `Sheet` shell
already never unmounts; today the caller does, by rendering `{record ?
<ReviewDocument .../> : null}` and destroying `ReviewDocument`'s own
`useState` every close. Keying `ReviewDocument` by the workspace id instead of
a document id, and toggling only `open`, lets the existing state survive a
close/reopen with no new state machinery. A full page reload is still allowed
to reset unsaved field edits - the server-persisted draft is the recovery
path for that case, unchanged.

### Definition of done

- [x] Closing and reopening the review retains in-session edits (typed text,
      not yet saved).
- [x] A reload or later login still resumes the persisted draft, unaffected
      by this change.
- [x] Covered by an extension to `onboarding-url.spec.ts`: type into a field,
      close the sheet, assert the dialog is hidden, reopen, assert the typed
      value is still there.

## W-11c: batch upload, replace, and polish

Branch `feat/w-11c-batch-review`, off `development` after W-11a and W-11b are
both merged. **Shipped to `development`** as `6eeb0df`, `cf9fcb3`, `7205e6b`,
`20d8ebc`, `72d153f`, `c802a50`, plus dashboard record `bc1f2ec`.

### User stories

- As an owner, I see a persistent `Documents ready to review` conversation
  card with the source count and a `Review documents` action whenever drafts
  remain.
- As an owner, uploading several files shows a live Processing/Ready/Failed
  row per file, and one combined review opens only once every file has
  settled.
- As an owner, I can add, replace, or remove sources from the review. Only
  draft or failed sources can be replaced. A replacement is processed before
  its old draft is deleted; a failed replacement preserves the old source.
- As an owner, I see owner offerings first and imported offerings in upload
  order, with each row labeled Owner or by its supporting filenames.
- As an owner, `Review all` starts at page 1, editing does not change pages,
  `Add offering` inserts into the owner group and focuses the new row, and the
  toolbar keeps `Review all` and `Add offering` at opposite ends responsively.
- As an owner, pagination says `Page X of Y` and `Showing A-B of N offerings`.
- As an owner, Business > Knowledge shows failed sources with Retry, Replace,
  and Remove. Retry recreates a draft for review and never publishes by
  itself.
- As an owner, I see a stable disclosure of where my documents are stored and
  that a configured AI provider processes them.

### Privacy disclosure

Onboarding displays (shortened per founder request, 2026-09-11, from the
original three-sentence copy below - kept short since onboarding has less
room and less patience for it than a settings page does):

> Your documents stay private to your business, and nothing answers customers
> until you review and save it.

Business > Knowledge displays a section titled `How your documents are used`:

> Original files are kept in your business's tenant-isolated Agencx file
> storage, and extracted sections and offerings are saved in its business
> database. A configured AI provider processes document text to organize it.
> Only content you approve can be used in customer answers. Files retained
> after a processing failure are kept so you can retry them. Replacing or
> removing a document removes the old source and its derived knowledge.

Use these stable product terms without vendor names. This is a product
disclosure, not a standalone legal Privacy Policy.

### Technical spec

- Replace the sequential per-file upload loop with a bounded-concurrency map
  (three at a time, five files maximum) over `Promise.allSettled`. Each entry
  flips its row from Processing to Ready or Failed; the combined review opens
  once every file has settled, not on the first accepted draft.
- Run `withCombinedOfferings` once over the union of all settled documents,
  not once per draft - running it per draft would duplicate owner offerings
  across every document.
- Order offerings owner-first, then imported in upload order, labeled Owner or
  by supporting filename(s).

### Definition of done

- [x] Multi-file processing settles every file before one combined review
      opens; the batch caps at five files, three concurrent.
- [x] Replace is safe on failure (old source preserved) and merges edits
      without silent loss, through the real UI.
- [x] Pagination, toolbar layout, field focus, keyboard access, and mobile
      widths are covered by browser tests.
- [x] Privacy copy matches this ticket exactly and contains no vendor name.
- [x] Covered by `knowledge-review.spec.ts` and an extension to
      `settings-knowledge.spec.ts`.
- [x] Manual pass: a real five-file upload through onboarding, per-file rows
      settling, edit/close/reopen, replace a source, retry a failed one,
      publish a batch where one document fails - checked at 375px and desktop.

## Whole-ticket verification

`make check` and `make eval-skip-llm` green per ticket as it lands. `make ci`
and `make test-e2e` green before W-11c merges (`make test-e2e` needs `make dev
&& make seed` first). W-11a/b/c all merged to `development`; `make check`,
`make ci`, `make test-e2e`, and the eval gate green per `progress.md`.
