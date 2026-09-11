# Agencx API contract

## Errors

JSON errors use RFC 9457 Problem Details with media type
`application/problem+json`:

```json
{
  "type": "about:blank",
  "title": "Validation failed",
  "status": 422,
  "detail": "One or more fields are invalid.",
  "instance": "urn:agencx:request:<request_id>",
  "code": "validation_failed",
  "request_id": "<request_id>",
  "errors": [{"pointer": "/field", "code": "required", "detail": "Field is required."}]
}
```

Malformed JSON is `400 malformed_request`. Semantic validation is `422
validation_failed`. Authentication is `401 unauthenticated` with
`WWW-Authenticate: Bearer`; authorization, missing resources, conflicts, rate
limits, upstream failures, and operational failures use stable local codes and
safe details. Rate limits include `Retry-After`.

Successful responses remain resource-oriented: reads and updates use 200,
creation uses 201, and successful commands or deletions use 204 with no body.
SSE failures after a stream starts use an `error` event containing `code`, safe
`detail`, and `request_id`.

The generated frontend OpenAPI types are refreshed with `npm run gen:types` and
checked without writing with `npm run gen:types -- --check`.

## Knowledge review contract (Phase 13, W-8)

The Phase 13 refinements (`spec/completed/13-walkthrough.md`, amended 2026-09-05)
define the contract used by onboarding and later knowledge review.

- **Draft offering identity, description, provenance, and source references.**
  `PendingOffering` carries a stable opaque `candidate_id`, description, price,
  provenance, and references to the source
  blocks that support the name, description, and price, so edits cannot
  migrate between items and every figure resolves deterministically (W-6,
  W-8).
- **Preserved complex-price context and explicit review issues.** Ranges,
  "from" prices, units, variants, bundles, surcharges, and currency stay
  surfaced with their source wording, with a review flag distinguishing
  absent, ambiguous, and conflicting prices (W-6).
- **Possible-match relationships and owner resolutions.** Proposed duplicate
  pairs and their owner decision (combine with which retained values, or keep
  both) round-trip on the existing save boundary; unresolved suggestions stay
  separate and saving never implies a merge (W-8).
- **Compatible defaults for existing drafts.** Drafts without the new
  metadata keep working and are not migrated eagerly; the new fields read
  through defaults (W-6/W-8 record compatibility).
- **Consistent candidate merge behavior across client and server.** One shared
  precedence policy is applied by both sides; the wire shape documents it
  rather than letting the two disagree (W-6).
- **Original source evidence.** `GET /api/knowledge/records/{document_id}/source`
  is owner-only and returns extracted original source text on demand. A legacy
  record returns its saved reviewed text with `is_fallback: true`.
- **Correction semantics through the existing onboarding message/update
  boundaries.** A turn that corrects previously captured fields is expressed
  through the existing onboarding message/update shapes; no new correction
  endpoint is planned (W-9).

No unrelated API redesign, new relational entities, or full pricing schema is
planned; the broader R-3 schema audit stays separate.
