# Phase 15: document review and privacy workflow

This ticket follows W-9's customer-agent contract work. It gives onboarding
and Business > Knowledge one retained document-review workspace, reliable
multi-file processing, safe replacement and retry behavior, partial
publication, and a stable product disclosure for document storage and AI
processing. It keeps the existing extraction and storage boundaries and does
not introduce a legal Privacy Policy.

## W-11: review documents without losing work

### Summary

Replace single-document review state with a retained workspace. Closing the
sheet hides it without discarding in-session edits. Drafts and successful
sources resume after reload or later login from persisted tenant-scoped data;
unsaved field edits may reset to the persisted extraction on reload.

Process selected files as one batch with per-file `Processing`, `Ready`, and
`Failed` states. Wait for every file to settle, then open one combined review
for successful files. Failed accepted uploads remain stored as reviewed drafts
for retry; unsupported or oversized files remain validation errors and are not
stored.

### User stories

- As an owner, I see a persistent `Documents ready to review` conversation card
  with the source count and a `Review documents` action whenever drafts remain.
- As an owner, I can add, replace, or remove sources from the review. Only
  draft or failed sources can be replaced. A replacement is processed before
  its old draft is deleted; a failed replacement preserves the old source.
- As an owner, my edits survive a source merge. Untouched offerings supported
  only by the replaced source are removed, edited unsupported offerings remain
  with `Not found in replacement`, and replacement price changes are
  suggestions rather than silent overwrites.
- As an owner, I see owner offerings first and imported offerings in upload
  order, with each row labeled Owner or by its supporting filenames.
- As an owner, `Review all` starts at page 1, editing does not change pages,
  `Add offering` inserts into the owner group and focuses the new row, and the
  toolbar keeps `Review all` and `Add offering` at opposite ends responsively.
- As an owner, non-offering facts are editable in collapsed source sections,
  fields have token-based borders and visible focus states, and pagination says
  `Page X of Y` and `Showing A-B of N offerings`.
- As an owner, a batch publication saves successful documents, leaves failed
  documents as reviewed drafts, updates onboarding offerings once, and withholds
  offerings supported only by failed documents.
- As an owner, Business > Knowledge shows failed sources with Retry, Replace,
  and Remove. Retry recreates a draft for review and never publishes by itself.

### Privacy disclosure

Onboarding displays:

> Your documents are stored in your business's tenant-isolated Agencx storage.
> A configured AI provider processes the text to organize facts and offerings.
> Documents cannot be used in customer answers until you review and save them.

Business > Knowledge displays a section titled `How your documents are used`:

> Original files are kept in your business's tenant-isolated Agencx file
> storage, and extracted sections and offerings are saved in its business
> database. A configured AI provider processes document text to organize it.
> Only content you approve can be used in customer answers. Files retained
> after a processing failure are kept so you can retry them. Replacing or
> removing a document removes the old source and its derived knowledge.

Use these stable product terms without vendor names. This is a product
disclosure, not a standalone legal Privacy Policy.

### Document API

Add `PUT /api/onboarding/knowledge/batch` with:

- Request: `documents: [{document_id, sections}]` and
  `offerings: [{offering, supporting_document_ids}]`.
- Response: `published`, `failed`, and the actually persisted
  `offering_candidates`.

Publish each document independently. Preserve submitted review data on failed
documents with a safe customer-facing error. Retain the existing
single-document endpoint and generated API-type workflow. Add failure metadata
to drafts and a retry-draft endpoint that uses existing document storage.

### Definition of done

- [ ] Closing and reopening the review retains in-session edits.
- [ ] Reload and later login resume persisted drafts and the onboarding
  conversation.
- [ ] Multi-file processing settles every file before one combined review opens.
- [ ] Replacement is safe on failure and merges edits without silent loss.
- [ ] Publication is partial, tenant-scoped, and never auto-publishes a retry.
- [ ] Pagination, toolbar layout, field focus, keyboard access, and mobile
  widths are covered by browser tests.
- [ ] Privacy copy matches this ticket exactly and contains no vendor name.
- [ ] `PUT /api/onboarding/knowledge/batch`, failure metadata, and retry are
  covered by API tests and generated frontend types.
- [ ] `make check`, `make ci`, `make test-e2e`, and `make eval-skip-llm` pass.
