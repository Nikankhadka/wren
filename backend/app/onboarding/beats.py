"""O-1/O-12: lean onboarding beats, the profile's single source of truth.

Free text is satisfied by extraction. Fixed chip and masked values use the
server-owned selection protocol so the saved beat, spoken question, and
composer cannot advance independently.

Two chips instead swap the composer to a different widget and submit nothing
until that widget's own value is sent - ``ChipSpec.widget`` says which. The
client never hardcodes a beat; it renders what the beat declares.

The same beats are asked of every tenant. Nothing here branches on a business
vertical (I8): ``business_type`` is captured as one more field and shapes the
tenant's system prompt at confirm, never the question set. ``abn``/``gst`` are
Australian by wording, not by vertical, and ``gst`` is conditional on the
answer to ``abn`` rather than on what the business does.

W-2 caps every beat at two asks. Which beat is required and which is skippable
follows one rule - skippable means nothing downstream reads it, or the owner
can still edit it after go-live - and ``next_beat`` runs the two passes that
cap implies.

W-7 adds the missing half: a beat now knows what a *plausible* answer looks
like (``valid``) and what to say when it does not get one (``reject``). Both
are deterministic and server-owned. W-9 makes the second half true: until then
``reject`` was read by nothing and a junk answer went back through the model,
which embellished the beat's ``example`` into a fact ("No worries at all,
Nikan!" - the owner addressed by the name beat's own example). A rejected beat
is now answered in the beat's own words with no model call at all.

W-9 also adds the voice beat - which of four voices the public assistant speaks
in - as one more chip beat. Its fourth chip swaps the composer to a text widget
for the owner's own bounded description, and every answer is validated here, so
no model ever chooses how the business sounds to its customers.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.shared.voice import CUSTOM_VOICE, CUSTOM_VOICE_MAX, VOICE_PRESETS

WidgetKind = Literal["text", "chips", "masked", "cta", "phone"]

# The sentinel an owner without an ABN leaves in the draft. A blank would leave
# the beat unsatisfied forever; "none" is a stated answer, and it is what makes
# the GST beat skip itself.
NO_ABN = "none"

# W-7 removed the "Skip for now" chip. A beat that will not fill is closed out
# by the ask cap instead, so there is no chip to explain and no skip vocabulary
# to teach. A skipped beat's field still stays empty and its key is remembered
# beside the draft, because `profile_tagline` reads `services` and `hours`
# straight into the public storefront subtitle and a sentinel there would show
# to customers. (NO_ABN is the opposite case: "no ABN" is a real answer that is
# meant to display.)


class ChipSpec(BaseModel):
    label: str
    value: str
    dashed: bool = False
    # O-6: when set, tapping this chip swaps the composer to that widget instead
    # of submitting the label. The phone pill and the ABN pill arrive this way.
    widget: WidgetKind | None = None


class InputSpec(BaseModel):
    kind: WidgetKind = "text"
    placeholder: str = ""
    chips: list[ChipSpec] = Field(default_factory=list)
    mask: str | None = None
    cta_label: str | None = None
    # O-6: the label welded inside the pill's left edge (the prototype's
    # `.abn-pre`). Presentation only - the value submitted is the field's own.
    prefix: str | None = None
    # O-6: prepend a one-tap chip carrying the address the owner logged in with.
    # The value is not in this payload on purpose - the client already holds it
    # in its session, and the server has no email column to read it from (the
    # address lives in Supabase auth, not in `users`). The beat declares that
    # the chip belongs here; the client supplies the label.
    suggest_owner_email: bool = False


@dataclass(frozen=True)
class Beat:
    """One question in the interview.

    W-2 splits the beats in two. A ``optional`` beat is one nothing downstream
    reads (``owner_display_name``, ``headcount``) or one the owner can still edit after
    go-live (``services`` via Business > What you offer, ``abn``/``gst`` via
    Business > details) - it resolves to its ``default`` or to nothing rather
    than being asked a third time. A required beat has neither property, so it
    is deferred to a second pass instead of being dropped.

    ``reject`` is what the beat says when it gets something that cannot be its
    answer, and it is spoken verbatim: a rejected beat's reply is the beat's own
    ``reject`` plus the beat's own ``ask``, with no model call at all, so there
    is nothing in that reply for a model to embellish. ``example`` is the
    concrete answer worked into the second-ask nudge, which is still
    model-composed - keep it free of anything a model could read back as a fact
    about this owner.

    ``valid`` is what makes a junk answer junk. ``complete`` only asks whether
    the field is non-empty, which is satisfied by "34234234" as a name; this
    asks whether the value is plausible *for this field*. It is deliberately
    permissive - it rejects what cannot be an answer, never what merely looks
    unusual, because a false rejection is worse than a wrong value the owner
    can still correct.
    """

    key: str
    label: str
    ask: str
    kind: WidgetKind
    complete: Callable[[dict[str, Any]], bool]
    chips: tuple[ChipSpec, ...] = ()
    mask: str | None = None
    prefix: str | None = None
    suggest_owner_email: bool = False
    optional: bool = False
    default: str = ""
    example: str = ""
    valid: Callable[[str], bool] | None = None
    reject: str = ""


# Deterministic per-beat plausibility checks (W-7). Nothing here calls a model,
# and nothing here is clever: each one names the single property without which
# the value cannot be an answer to its question.

# Two or more letters in a row - enough to tell a word from a serial number.
_WORDISH = re.compile(r"[^\W\d_]{2,}", re.UNICODE)
_DAYS = (
    "mon",
    "tue",
    "wed",
    "thu",
    "fri",
    "sat",
    "sun",
    "weekday",
    "weekend",
    "daily",
    "every day",
    "always",
    "24",
)


def _wordish(value: str) -> bool:
    """A name, a business name, a business type, a service list: needs a word.

    Digits are allowed *inside* the answer ("Cafe 21", "3 Chairs Dental") - the
    test is that a word is present at all, not that digits are absent.
    """
    return _WORDISH.search(value) is not None


def _hours_like(value: str) -> bool:
    """Opening hours: a time of day, a day of the week, or "always"."""
    lowered = value.casefold()
    return any(char.isdigit() for char in value) or any(day in lowered for day in _DAYS)


def _contact_like(value: str) -> bool:
    """A way to reach the business: an email address or a phone number."""
    if "@" in value and "." in value.rsplit("@", 1)[-1]:
        return True
    return sum(char.isdigit() for char in value) >= 6


def _complete(field: str) -> Callable[[dict[str, Any]], bool]:
    return lambda draft: bool(draft.get(field))


def _gst_complete(draft: dict[str, Any]) -> bool:
    """GST only applies to a business that has an ABN.

    An owner who answered "no, not yet" is not asked a follow-up about a
    registration they cannot hold - the prototype skips straight past it. This
    is a conditional beat expressed in the predicate the gate already calls, so
    it needs no branching anywhere else.
    """
    if str(draft.get("abn", "")).strip().lower() == NO_ABN:
        return True
    return bool(draft.get("gst"))


BEAT_ORDER: tuple[Beat, ...] = (
    Beat(
        key="owner_display_name",
        label="your name",
        # W-7: "What name would you like me to use?" landed right after a
        # sentence about setting the *business* up, and read as a question
        # about the business name. The two name beats now say which is which.
        # W-9: the opening line the controller composes says the business comes
        # next, so this asks one thing and says nothing about what follows.
        ask="Before we start, what should I call you?",
        kind="text",
        complete=_complete("owner_display_name"),
        # Nothing downstream reads the owner's name, and it cannot be guessed,
        # so this is the one beat that skips to a genuine blank.
        optional=True,
        valid=_wordish,
        reject="That doesn't look like a name.",
        example='just a first name is plenty - "Nikan"',
    ),
    Beat(
        key="business_name",
        label="business name",
        ask="What does the business go by?",
        kind="text",
        complete=_complete("business_name"),
        valid=_wordish,
        reject="That doesn't look like a business name.",
        example='even a short one works - "Bytefix" or "Sababa"',
    ),
    Beat(
        key="business_type",
        label="business type",
        ask="In a few words, what kind of business is it?",
        kind="text",
        complete=_complete("business_type"),
        valid=_wordish,
        reject="I didn't catch what kind of business that is.",
        example='a few words is plenty - "phone repair shop" or "family dental practice"',
    ),
    Beat(
        key="headcount",
        label="team size",
        ask="Is it just you, or do you work with a team?",
        kind="text",
        complete=_complete("headcount"),
        chips=(
            ChipSpec(label="Just me", value="just me"),
            ChipSpec(label="Got a team", value="got a team"),
        ),
        # Read by nothing downstream, and solo is the overwhelming majority of
        # businesses that self-onboard, so an unanswered team size takes it.
        optional=True,
        default="just me",
        example='"just me" or "there are four of us"',
    ),
    Beat(
        key="hours",
        label="opening hours",
        # W-7: W-2's wording was two questions joined by "and", which is the
        # thing the interview is not supposed to do. One question, both halves.
        ask="What days and hours are you open?",
        kind="text",
        complete=_complete("hours"),
        valid=_hours_like,
        reject="I couldn't read that as opening hours.",
        example='"9 to 5, Monday to Friday" - or "online, always open"',
    ),
    Beat(
        key="services",
        label="what you offer",
        ask="What would you like customers to know you offer?",
        kind="text",
        complete=_complete("services"),
        # Editable after go-live at Business > What you offer, and an uploaded
        # menu or price list can fill the catalog instead.
        optional=True,
        valid=_wordish,
        reject="I couldn't read that as something you offer.",
        # I8: the example teaches the shape of the answer - a few items, plainly
        # named - and names no trade, so a cafe is never nudged in a salon's
        # vocabulary (W-9).
        example="two or three of the things you do most, in your own words, is plenty",
    ),
    Beat(
        key="customer_voice_preset",
        label="assistant voice",
        # I8: the question is about wording, warmth and pacing - never about
        # what the business does - so it is the same question for every trade.
        ask="How should your assistant sound to customers?",
        kind="text",
        complete=_complete("customer_voice_preset"),
        chips=(
            ChipSpec(label="Warm and casual", value=VOICE_PRESETS[0]),
            ChipSpec(label="Clear and professional", value=VOICE_PRESETS[1]),
            ChipSpec(label="Direct and concise", value=VOICE_PRESETS[2]),
            # The fourth chip answers nothing on its own: it swaps the composer
            # to a text widget and the owner's own description is what gets
            # sent, bounded so a voice cannot become a second system prompt.
            ChipSpec(label="Describe it myself", value=CUSTOM_VOICE, dashed=True, widget="text"),
        ),
        # Editable after go-live at Business > details, and the first preset is
        # what an unanswered voice resolves to, so it never blocks the interview.
        optional=True,
        default=VOICE_PRESETS[0],
        example="pick one, or describe the voice in your own words",
    ),
    Beat(
        key="contact",
        label="contact details",
        ask="How should customers reach you?",
        kind="text",
        complete=_complete("contact"),
        # The business contact is often the address the owner logged in with,
        # and when it is not, the pill is right there. "Phone number" swaps the
        # composer to the country-code pill rather than submitting the words.
        chips=(ChipSpec(label="Phone number", value="phone", dashed=True, widget="phone"),),
        suggest_owner_email=True,
        valid=_contact_like,
        reject="That doesn't look like an email address or a phone number.",
        example="an email or a phone number - whichever you'd rather they used",
    ),
    Beat(
        key="abn",
        label="ABN",
        ask="Do you have an ABN?",
        kind="text",
        complete=_complete("abn"),
        mask="XX XXX XXX XXX",
        prefix="ABN",
        chips=(
            ChipSpec(label="Yes", value="yes", widget="masked"),
            ChipSpec(label="No", value=NO_ABN),
        ),
        # Editable after go-live at Business > details > ABN & Tax. "No" is
        # already one tap away, so an unanswered ABN takes the same value.
        optional=True,
        default=NO_ABN,
        example='tap "No" if you do not have one yet',
    ),
    Beat(
        key="gst",
        label="GST registration",
        ask="Are you registered for GST?",
        kind="text",
        complete=_gst_complete,
        chips=(
            ChipSpec(label="Yes", value="yes"),
            ChipSpec(label="Not yet", value="not yet"),
        ),
        # Rarely reached: defaulting `abn` to NO_ABN satisfies this one too.
        optional=True,
        default="no",
        example='"yes" or "not yet"',
    ),
)

BEATS: dict[str, Beat] = {beat.key: beat for beat in BEAT_ORDER}

# The prototype's placeholder convention: a beat offering chips invites typing
# past them ("or type…"), it never blocks free text.
CHIPPED_PLACEHOLDER = "or type…"


def next_beat(
    draft: dict[str, Any],
    skipped: Sequence[str] = (),
    deferred: Sequence[str] = (),
) -> Beat | None:
    """The beat to ask now, or None when nothing is left to ask.

    W-2 runs the interview in two passes. ``skipped`` beats are gone for good.
    A ``deferred`` beat is a required one the owner did not answer in two asks:
    it is held back so the interview keeps moving, and comes back once every
    other beat has been through pass one. That way a repeated question is never
    adjacent to itself, which is what made the founder's transcript read as a
    loop.
    """
    pending = [beat for beat in BEAT_ORDER if not beat.complete(draft) and beat.key not in skipped]
    if not pending:
        return None
    first_pass = [beat for beat in pending if beat.key not in deferred]
    # Nothing left in pass one means the deferred beats are all that remain.
    return first_pass[0] if first_pass else pending[0]


def input_spec(beat: Beat) -> InputSpec:
    """The composer widget for a beat."""
    return InputSpec(
        kind=beat.kind,
        # W-3: a non-chipped beat's placeholder used to repeat `beat.ask`, but
        # the assistant's question is already the in-thread context - the
        # field's accessible label carries the affordance instead (see
        # CommandPill's `ariaLabel` prop). A chipped beat still teaches "or
        # type…" past its chips.
        placeholder=CHIPPED_PLACEHOLDER if beat.chips else "",
        chips=list(beat.chips),
        mask=beat.mask,
        prefix=beat.prefix,
        suggest_owner_email=beat.suggest_owner_email,
    )


def apply_selection(draft: dict[str, Any], key: str, values: list[str]) -> str:
    """Validate and store one deterministic answer, returning its user label."""
    beat = BEATS.get(key)
    if beat is None or len(values) != 1:
        raise ValueError("select one valid answer")
    value = values[0].strip()
    labels = {chip.value: chip.label for chip in beat.chips if chip.widget is None}

    if key == "headcount" and value in labels:
        draft[key] = value
        return labels[value]
    if key == "abn":
        if value == NO_ABN:
            draft[key] = value
            return labels[value]
        digits = "".join(char for char in value if char.isdigit())
        if len(digits) == 11:
            draft[key] = digits
            return value
    if key == "gst" and value in labels:
        draft[key] = "yes" if value == "yes" else "no"
        return labels[value]
    if key == "customer_voice_preset":
        # W-9: a preset is one of a fixed vocabulary; anything else the owner
        # sends on this beat is their own bounded description of the voice. The
        # custom chip's own value is reserved - tapping it swaps the composer
        # and submits nothing, so arriving here it is not a description.
        if value in labels:
            draft[key] = value
            draft.pop("customer_voice_custom_style", None)
            return labels[value]
        if value != CUSTOM_VOICE and 0 < len(value) <= CUSTOM_VOICE_MAX:
            draft[key] = CUSTOM_VOICE
            draft["customer_voice_custom_style"] = value
            return value
    raise ValueError("select one valid answer")


# W-9 US-1: what the composer offers while a name waits to be confirmed. One
# chip commits the proposal; typing past it is a new proposal, never a
# rejection, which is why the pill stays and the placeholder still invites it.
NAME_CONFIRM_INPUT = InputSpec(
    kind="text",
    placeholder=CHIPPED_PLACEHOLDER,
    chips=[ChipSpec(label="Yes", value="yes")],
)


# The optional website/documents ask (see agent._completion_reply) is not a
# beat - it never gates the profile - but it still needs a text composer, so it
# reuses the same InputSpec shape as the text beats it follows.
KNOWLEDGE_INPUT = InputSpec(kind="text", placeholder='Paste a link, attach a file, or say "skip"')


def check_completeness(draft: dict[str, Any], skipped: Sequence[str] = ()) -> list[str]:
    """Labels of every unsatisfied beat the owner has not skipped.

    A deferred beat is deliberately not excused here - pass two has to finish
    before go-live, or a required field would reach the storefront empty.
    """
    return [
        beat.label for beat in BEAT_ORDER if not beat.complete(draft) and beat.key not in skipped
    ]
