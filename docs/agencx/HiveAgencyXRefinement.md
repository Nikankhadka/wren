# Agencx Phase 1 Refinement: prototype, documentation, and incremental tickets

## Context

Refine the existing Agencx application using selected Hivee workflows and an original Agencx visual language. Preserve working behavior, especially onboarding and document review.

The immediate deliverables are **a new prototype version and implementation-ready documentation**. Production changes will follow as small, connected tickets implemented by GPT Luna. Astra retains design judgment and review.

## Prototype and documentation

Create `agencx-prototype-v7.html` beside the existing v6 prototype. Preserve v6 unchanged.

Reuse its useful navigation, screen, and sheet patterns, but reconcile obsolete prototype behavior with the running application first. Keep the current email login and onboarding flow. Exclude old payment, scheduling, and Copilot screens from the Phase 1 experience.

The new prototype must provide:

- Connected owner and customer journeys, with desktop and mobile layouts.
- Four switchable businesses: cafe, retail/repair, dental clinic, and general clinic.
- Shared simulated state: offering edits affect the Business page; customer handoffs appear in the owner queue; owner replies appear in the customer conversation.
- Working navigation, editors, uploads, review decisions, filters, and recovery states.
- Simulated processing and responses, without production API calls.
- Conversation continuity through same-tab refresh using isolated prototype session state.
- A short introductory comparison, guided walkthroughs, and free exploration.

Update the canonical frontend design document, PRD glossary, decision ledger, specification index, prototype references, and progress dashboard. Add `17-phase-one-refinement.md` with the ticket series. The companion UI spec for the implementing frontend work is `design/frontend-refinement.md` - every RF ticket maps to its screens, states, and prototype references there.

Include a coverage ledger for every Hivee reference area: current Agencx behavior, Hivee behavior, adopted decision, capability gap, prototype reference, and implementation ticket. Distinguish shipped behavior from proposed changes.

Use these canonical terms consistently: **Business page, offering, preferred name, conversation, conversation reference, issue, handoff, takeover, handback, resolution, price summary, and request**. A request awaits business acceptance; it is not a confirmed order or booking.

## Agreed behavior

### Preserve the foundation

- Retain Home, Chats, and Business navigation.
- Preserve current onboarding sequence, confirmations, and completion flow.
- Allow go-live without uploaded documents or confirmed offerings, with clear next steps.
- Preserve document-review drafts, source evidence, explicit price decisions, replacement, retry, and independent publication.

### Improve business maintenance

- Add core business-detail editing after launch, including name, hours, description, and business contact information.
- Keep the public address stable when the business name changes.
- Improve cover and offering-image upload, preview, replacement, and removal.
- Use searchable, category-grouped offerings. Equal prices do not merge distinct offerings.
- Support fixed prices and separate owner-confirmed pricing wording. Display-only wording must not be treated as a calculable fixed amount.
- Use contextual owner edit shortcuts opening the same editors as Business, with explicit Save and Cancel.

### Improve customer query handling

- Keep the Business page browse-first, with clearly labeled chat access.
- Use a desktop chat side panel and a full-height mobile sheet.
- Preserve editable contextual questions and existing composer text; do not send automatically.
- Answer from confirmed business information. Explain uncertainty and offer help rather than inventing facts.
- Answer while asking for a preferred name, with at most two opening-phase name requests.
- Accept a first name or nickname without verification. Collect no customer phone number or email.
- Require a name for customer-requested handoff. Internal operational alerts may still use the conversation reference.
- Provide a visible **Ask for a person** action.
- Preserve the conversation while browsing and through same-tab refresh.
- Keep unanswered questions in All when the customer does not accept handoff, unless an operational failure requires attention.

### Improve owner handling

- Open Chats in **Needs you**, containing unresolved issues and active human-handled conversations.
- Retain All and Human handled views.
- Apply filtering, searching, and pagination across the complete conversation dataset.
- Show one conversation row with identity/reference, attention reason, handler, and waiting time.
- Keep takeover, reply, issue resolution, and handback distinct.
- Resolve specific issues explicitly; neither replying nor handing back silently resolves them.

## Small delivery batches for Luna

Each ticket must specify its visible outcome, current/proposed behavior, prototype states, dependencies, API changes, acceptance scenarios, and regression checks. Backend and frontend work necessary for one usable outcome belong together.

### 1. Shared presentation

- **RF-1**: Refine shared typography, surfaces, controls, responsive navigation, and focus behavior while preserving routes and flow order.

### 2. Business maintenance

- **RF-2**: Add core business-detail editing and immediate consistency with customer answers.
- **RF-3**: Add offering search and category grouping.
- **RF-4**: Add explicit pricing wording across editing, publication, and customer display.
- **RF-5**: Refine cover and offering-image workflows.
- **RF-6**: Clarify the existing document-review workspace without changing its publication semantics.

### 3. Business page and customer presentation

- **RF-7**: Refine Business page composition and contextual owner editing.
- **RF-8**: Introduce desktop customer chat panels and mobile sheets.
- **RF-9**: Align existing offering and price-summary cards with the refined experience.

### 4. Customer identity and continuity

- **RF-10**: Add preferred-name capture, correction, and persisted prompt limits.
- **RF-11**: Add the visible human-help action and name-gated requested handoff.
- **RF-12**: Restore conversation content, structured cards, and relevant state after same-tab refresh.
- **RF-13**: Improve failed-send recovery and draft preservation without unsafe automatic replay.

### 5. Owner work queue

- **RF-14**: Add complete-dataset queue filtering, searching, pagination, and attention counts.
- **RF-15**: Introduce desktop split-pane Chats while preserving mobile navigation.
- **RF-16**: Bring explicit issue resolution into the conversation workspace.

### 6. Integrated verification

- **RF-17**: Complete the four-business walkthroughs and record visual and behavioral evidence.

RF-1 precedes visual ports. RF-7 follows the business-maintenance tickets; RF-8 and RF-9 follow it. RF-11 follows name capture, and continuity covers those resulting states. Queue filtering precedes split-pane work, which precedes integrated issue resolution.

Existing checks run within every ticket; RF-17 verifies the assembled experience rather than postponing testing.

## Verification and boundaries

Use a dedicated branch per implementation ticket and preserve the current checkout's unrelated work. Keep contract changes backward compatible so intermediate deployments remain usable.

Verify:

- Existing login, onboarding, document review, pricing safeguards, and tenant isolation.
- All four businesses using identical workflow code and configuration-driven content.
- Name refusal, correction, duplicate names, and handoff without customer contact collection.
- More than 200 conversations, including older unresolved issues beyond the first page.
- Owner/customer transcript consistency across takeover, reply, resolution, handback, and refresh.
- Long offerings, missing images, unpriced items, pricing wording, and partial processing failures.
- Mobile and desktop layout, keyboard access, focus restoration, and scroll preservation.

Future request submission and business acceptance remain separately documented. Owner Copilot, image understanding, galleries, independent page-pause controls, scheduling, payments, invoices, billing, external reviews, and account-management additions remain deferred.

## Definition of completion

This design task is complete when the documentation and v7 prototype agree, every included workflow has an implementation ticket, and Luna can implement each ticket without deciding product behavior.