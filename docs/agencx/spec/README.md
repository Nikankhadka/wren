# Agencx specs and user stories

The spec set records the Agencx change build. Each ticket includes its intent,
acceptance criteria, implementation constraints, verification, and definition
of done. One ticket equals one commit, and commit messages start with the
ticket id when a ticket is implemented.

## How to read a ticket

| Section | Purpose |
|---|---|
| Summary | What the ticket delivers |
| Why | The product promise or measured problem |
| User stories | Persona-specific acceptance criteria |
| Design reference | The prototype screen for UI work |
| Technical spec | The intended implementation shape |
| Tests | The checks required for completion |
| Definition of done | The final completion checklist |

Tickets are written before implementation. Amendments are written after a
founder walkthrough exposes a change inside a closed phase. Amendments retain
their checked acceptance criteria and do not gain invented retrospective
technical sections. The amendments are O-6 through O-12, E-6, and the Phase 13
amendment record inside `13-walkthrough.md` (2026-09-05), which refines W-3
through W-6, adds W-8 and W-9, and distinguishes specification updates from
implementation delivery.

## Active and completed work

Active phase files contain unresolved tickets only:

| Location | Contents |
|---|---|
| [`active/08-deferred.md`](active/08-deferred.md) | B-2, D-1, D-3 |
| [`active/12-refinement.md`](active/12-refinement.md) | R-3, R-4, R-5 |
| [`active/14-schema-drop.md`](active/14-schema-drop.md) | W-10 |
| [`active/16-auth-otp-reliability.md`](active/16-auth-otp-reliability.md) | W-12, W-13 |

Completed phase files preserve the detailed records for shipped work:

| Location | Phase |
|---|---|
| [`completed/01-foundation.md`](completed/01-foundation.md) | Foundation |
| [`completed/02-onboarding.md`](completed/02-onboarding.md) | Onboarding |
| [`completed/03-chat-spine.md`](completed/03-chat-spine.md) | Chat spine |
| [`completed/04-chat-grounding.md`](completed/04-chat-grounding.md) | Chat grounding |
| [`completed/05-business-page.md`](completed/05-business-page.md) | Business page |
| [`completed/06-polish.md`](completed/06-polish.md) | Polish |
| [`completed/07-hygiene.md`](completed/07-hygiene.md) | Hygiene |
| [`completed/09-devex.md`](completed/09-devex.md) | Developer experience |
| [`completed/10-deploy.md`](completed/10-deploy.md) | Deployment |
| [`completed/11-offerings-media.md`](completed/11-offerings-media.md) | Offerings and media |
| [`completed/13-walkthrough.md`](completed/13-walkthrough.md) | Walkthrough fixes |
| [`completed/15-document-review.md`](completed/15-document-review.md) | Document review and privacy workflow |

Completed R-1 and R-2 refinement records are preserved in
[`docs/archive/phase1-complete/12-refinement-r1-r2.md`](../../archive/phase1-complete/12-refinement-r1-r2.md).

When a phase's tickets are complete, move its file from `active/` to
`completed/` with `git mv`, then update [progress.md](../progress.md).

## Building UI

The current prototype is
[`agencx-prototype-v6.html`](../design/prototypes/agencx-prototype-v6.html).
Port its structure, states, spacing, and interaction vocabulary. Use prototype
behaviour, not prototype copy or hex values. Visual values belong in
`frontend/src/styles/theme.css`.

The former storefront prototype is preserved at
[`agencx-storefront-customer-v3.html`](../../archive/prototypes/agencx-storefront-customer-v3.html)
for interaction vocabulary only. It is not a current navigation reference.

## Phase sequence

Phase 1 delivered onboarding, customer chat, and the business page. The
supporting phases landed in this order:

1. Foundation and onboarding
2. Chat spine and grounding
3. Business page and polish
4. Hygiene and containerized developer experience
5. Deployment
6. Offerings and media
7. Phase 1 refinement
8. Walkthrough fixes

The active refinement phase is hardening, not new product scope. B-2, D-1, and
D-3 remain deferred to Phase 2. Payments, scheduling, invoicing, leads, and
other Stage 2 work remain outside this spec set.

The walkthrough phase (`W-1` through `W-9`) closes defects a founder
walkthrough found in already-shipped work: the home escalation queue, the
onboarding interview, customer chat grounding, the review sheet, and
conversational correction. It is a second bug-fix pass on Phase 1 surfaces,
not new product scope. W-1, W-2, and W-7 are delivered; W-3 through W-6, W-8,
and W-9 were refined and added by the 2026-09-05 amendment and remain open
specifications.

The walkthrough spec file also carries the amendment record for the second
round ([`13-walkthrough.md`](active/13-walkthrough.md)), which keeps the
reported observations, the found clarified preferences, the implementation
evidence, and the boundary between symptoms, confirmed code behavior,
suspected causes, and outstanding browser verification beside the tickets it
feeds.
