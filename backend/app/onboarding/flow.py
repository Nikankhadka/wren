"""O-1: onboarding schemas - the lean flat profile.

The pre-Agencx 16-beat, section-per-concern profile (business/identity/tone/
services/pricing_rules/escalation/tax/payment/kyc/readback) is collapsed to a
single flat profile - the PRD spine step 2 fields - extracted in one pass and
merged by one ``save_profile`` tool. Prices are absent by design: Stage 1
onboarding captures what the business is, not what it charges (the money
boundary stays with the customer assistant and the pricing engine).
"""

from __future__ import annotations

from hashlib import sha256
from typing import Literal
from unicodedata import normalize

from pydantic import BaseModel, Field, field_validator, model_validator

from app.shared.voice import CUSTOM_VOICE, CUSTOM_VOICE_MAX, DEFAULT_VOICE_PRESET


class ProfileDraft(BaseModel):
    """The lean business profile (PRD spine step 2)."""

    # W-9: the owner's own name, private to onboarding and the owner-facing
    # console. It is never the business's public identity - the two were one
    # `or` apart in the go-live line before this name said which is which.
    owner_display_name: str = ""
    business_name: str = ""
    business_type: str = ""
    headcount: str = ""
    hours: str = ""
    services: str = ""
    contact: str = ""
    # O-6: an ABN is what a business puts on an invoice, so the interview asks
    # for it. "none" is the stated answer of an owner who does not have one -
    # a distinct value from "not asked yet", which is the empty string.
    abn: str = ""
    gst: str = ""
    # W-9: how the public assistant sounds. Server-owned - the voice beat's own
    # chips write these through `beats.apply_selection`, and `tools.save_profile`
    # refuses them, so extraction can never put words in the owner's mouth here.
    customer_voice_preset: str = ""
    customer_voice_custom_style: str = ""


def customer_voice_for(profile: ProfileDraft) -> dict[str, str | None]:
    """The structured voice a confirmed tenant stores at ``config->customer_voice``.

    One shape, written here and read by the customer assistant: a preset key and
    (only for ``custom``) the owner's bounded description. An owner who never
    reached the voice beat takes the same default the beat itself resolves to.
    """
    preset = profile.customer_voice_preset or DEFAULT_VOICE_PRESET
    style = profile.customer_voice_custom_style.strip()[:CUSTOM_VOICE_MAX]
    if preset != CUSTOM_VOICE:
        style = ""
    return {"preset": preset, "custom_style": style or None}


def system_prompt_for(business_name: str, business_type: str) -> str:
    """The persona a confirmed tenant's assistant runs under.

    ``business_type`` is the owner's own free text, so it gets its own sentence
    rather than an apposition - "Bytefix Repairs, phone repair shop" and
    "Northgate Family Dental, A three-chair practice..." both read badly. Used
    by the confirm write path and by the seeds that pre-onboard a demo tenant,
    so both produce byte-identical prompts.
    """
    return (
        f"You are the assistant for {business_name}. "
        f"About the business: {business_type.rstrip('.')}. "
        "Answer only from the business's own material; when the answer isn't "
        "there, say so and offer to have the owner follow up."
    )


# W-9 US-3: what a correction can target. ``unresolved_name`` is not a field -
# it is how the extractor says "they asked me to change the name and I cannot
# tell which one", so the server asks one deterministic clarification instead of
# guessing between the owner's name and the business's.
CorrectionTarget = Literal[
    "owner_display_name",
    "business_name",
    "business_type",
    "headcount",
    "hours",
    "services",
    "contact",
    "abn",
    "gst",
    "unresolved_name",
]

UNRESOLVED_NAME = "unresolved_name"


class FieldCorrection(BaseModel):
    """One already-captured field the owner corrected, from any beat.

    ``raw`` keeps the owner's own words as the evidence behind ``value``, so a
    correction the server later rejects can still be read back honestly, and
    ``normalization`` says how much the extractor changed on the way (US-6: a
    name, a brand, an identifier, or an amount is never quietly tidied).
    """

    field: CorrectionTarget
    value: str = Field(default="", max_length=2000)
    raw: str = Field(default="", max_length=2000)
    normalization: Literal["none", "spelling", "spacing", "capitalization"] = "none"


class OfferingOperation(BaseModel):
    """W-9 US-4: one explicit edit to the offering list.

    ``rename`` keeps the same item under a new name, so every W-6 provenance
    field survives it; ``replace`` swaps one item for a different one and
    therefore starts that item's provenance over.
    """

    op: Literal["add", "rename", "remove", "replace"]
    name: str = Field(min_length=1, max_length=200)
    new_name: str = Field(default="", max_length=200)


class DraftUpdate(BaseModel):
    """Per-turn structured extraction result: what the owner stated this turn.

    Transient - never persisted. Any non-null ``profile`` field is merged into
    the accumulated draft by ``save_profile``; ``off_topic`` / ``meta_reply``
    drive the reply directive. The server's current beat owns the next question.

    W-9 adds the two things an owner does that are not answers to the pending
    question: correcting a field captured earlier, and editing the offering
    list. Neither carries a number - W-6's frozen-money discipline is
    unconditional, so no schema in this file has a numeric field the model
    fills in.
    """

    off_topic: bool = False
    profile: ProfileDraft | None = None
    meta_reply: str | None = None
    offering_names: list[str] | None = None
    corrections: list[FieldCorrection] | None = None
    offering_ops: list[OfferingOperation] | None = None
    # W-7: the extractor's verdict on whether this reply is a genuine, plausible
    # answer to the field that was asked this turn. Paired with the server's own
    # deterministic `Beat.valid` check - either may veto - so a word-shaped
    # nonsense answer the regex waves through ("asdfgh" for a business type) is
    # still caught, and a value the model hallucinated into a field the regex
    # rejects still bounces. ``None`` when no field was asked (the opening turn).
    answered_asked: bool | None = None


class PendingOffering(BaseModel):
    """An offering waiting for owner review before it reaches the catalog."""

    name: str = Field(min_length=1, max_length=200)
    # A deterministic opaque id lets the review UI key edits by the candidate,
    # not its mutable name or list position. Existing drafts get this on read
    # and persist it the next time the owner saves.
    candidate_id: str = Field(default="", max_length=80)
    description: str = Field(default="", max_length=2000)
    price_cents: int | None = Field(default=None, ge=0)
    sources: list[Literal["owner", "document"]] = Field(default_factory=list, validate_default=True)
    source_references: list[SourceReference] = Field(default_factory=list)
    # W-6: a price the offering row cannot represent - a range, a "from" price,
    # a rate - kept as the source's own wording so the owner sees what the
    # document actually said instead of a number picked out of it.
    price_note: str = Field(default="", max_length=400)
    # W-6: this candidate needs a decision before it is right. Set when the
    # price is complex or could not be bound to this item unambiguously; not set
    # merely because a price is absent, which is an ordinary thing for a source
    # to be silent about.
    needs_review: bool = False
    # W-8: ids of candidates that might be this same item. They are never
    # merged automatically; the owner can keep both or combine explicitly.
    possible_matches: list[str] = Field(default_factory=list)
    # W-6: the competing amounts when two sources price one item differently.
    # The owner picks; nothing here decides for them.
    price_options: list[int] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("offering name must not be empty")
        return value

    @field_validator("sources")
    @classmethod
    def _require_source(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value)) or ["owner"]

    @model_validator(mode="after")
    def _default_candidate_id(self) -> PendingOffering:
        if not self.candidate_id:
            self.candidate_id = stable_candidate_id(self.name)
        return self


class SourceReference(BaseModel):
    """Verbatim evidence supporting a candidate field in its source."""

    block: str = Field(min_length=1, max_length=80)
    excerpt: str = Field(min_length=1, max_length=2000)
    supported_fields: list[Literal["name", "description", "price"]] = Field(default_factory=list)


def stable_candidate_id(name: str) -> str:
    """Stable opaque ids for extracted and legacy candidates alike."""
    normalized = " ".join(normalize("NFKC", name).casefold().split())
    return f"off_{sha256(normalized.encode()).hexdigest()[:20]}"


def normalize_pending_offerings(raw: object) -> list[PendingOffering]:
    """Read legacy candidates into the current identity-based wire shape."""
    offerings: list[PendingOffering] = []
    for item in raw if isinstance(raw, list) else []:
        try:
            offerings.append(
                PendingOffering.model_validate(
                    {"name": item, "sources": ["owner"]} if isinstance(item, str) else item
                )
            )
        except (TypeError, ValueError):
            continue
    by_name = {" ".join(item.name.casefold().split()): item.candidate_id for item in offerings}
    return [
        item.model_copy(
            update={
                "possible_matches": [
                    by_name.get(" ".join(match.casefold().split()), match)
                    for match in item.possible_matches
                ]
            }
        )
        for item in offerings
    ]


def merge_offerings(existing: PendingOffering, incoming: PendingOffering) -> PendingOffering:
    """Combine two candidates for the same offering, document values winning.

    **This is the offering precedence policy, in one place.** Every merge in the
    system runs through here - the onboarding record combining an owner-typed
    name with a document candidate, and W-6's reconciliation of the same item
    found twice across two segments of one document. It used to be reimplemented
    in the browser with the opposite precedence, which is exactly the kind of
    disagreement the single policy exists to prevent.

    The rules:

    - **Document wins.** W-7: when an uploaded document and an owner-typed name
      describe the same thing, the document's name, price and description are
      authoritative - the founder asked that the PDF reference always win an
      overlap. The name follows the document so its spelling and punctuation are
      preserved.
    - **Sources union**, so the review sheet can show it came from both.
    - **Conflicting prices do not resolve silently.** W-6: two different amounts
      for one item become ``price_options`` for the owner to choose between,
      rather than one of them quietly winning.
    - **Review state and match suggestions survive** the merge; a flag raised by
      either candidate stays raised.

    The owner can override any of it on the review sheet before publish.
    """
    pair = (existing, incoming)
    document = next((item for item in pair if "document" in item.sources), None)
    preferred: tuple[PendingOffering, ...] = ((document,) if document else ()) + pair
    price_cents = next(
        (item.price_cents for item in preferred if item.price_cents is not None), None
    )
    description = next((item.description for item in preferred if item.description), "")
    sources = list(dict.fromkeys([*existing.sources, *incoming.sources]))
    name = document.name if document else existing.name
    offered = [item.price_cents for item in pair if item.price_cents is not None]
    conflicting = sorted({*offered, *existing.price_options, *incoming.price_options})
    return PendingOffering(
        name=name,
        candidate_id=document.candidate_id if document else existing.candidate_id,
        description=description,
        price_cents=price_cents,
        sources=sources,
        source_references=list(
            {
                (reference.block, reference.excerpt, tuple(reference.supported_fields)): reference
                for reference in [*existing.source_references, *incoming.source_references]
            }.values()
        ),
        price_note=next((item.price_note for item in preferred if item.price_note), ""),
        needs_review=existing.needs_review or incoming.needs_review,
        possible_matches=sorted({*existing.possible_matches, *incoming.possible_matches}),
        price_options=conflicting if len(conflicting) > 1 else [],
    )
