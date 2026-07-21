"""T-006: the conversational onboarding state machine.

A guided, explicitly-ordered set of stages - not an open-ended interviewer.
Each stage (except ``knowledge_prompt``, which needs no extraction) makes one
``LLMProvider.extract`` call to turn the admin's free-text reply into a typed
draft; the stage then advances deterministically. Prompts are generic
wording only - nothing here may branch on a business vertical (domain-agnostic
hard rule, Wren_AGENTS.md section 9).

Money handling: the admin is the source of every price mentioned here (their
own free-text answer), so the model's job is transcription of a number they
already said, never invention of one. To keep the actual monetary arithmetic
itself deterministic and server-side (matching the ticket's "amounts
converted to integer cents server-side" instruction and the spirit of the
deterministic-pricing hard rule), the model only extracts a plain dollar
float; the cents conversion happens in this module's own Python code, never
inside the model call.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.llm.provider import LLMProvider

STAGE_ORDER: tuple[str, ...] = (
    "identity",
    "tone",
    "services",
    "pricing_rules",
    "escalation_threshold",
    "knowledge_prompt",
    "confirm",
)

_SYSTEM_PROMPT_PREFIX = (
    "You are helping onboard a new small business onto a support-and-sales "
    "platform. Extract only what the admin actually said - never invent "
    "services, prices, or details they didn't mention. "
)


class IdentityDraft(BaseModel):
    description: str


class ToneDraft(BaseModel):
    tone: str


class CatalogItemDraft(BaseModel):
    name: str
    description: str = ""
    price_dollars: float | None = None


class ServicesDraft(BaseModel):
    items: list[CatalogItemDraft] = Field(default_factory=list)


class PricingRuleDraft(BaseModel):
    code: str
    label: str
    # Optional so the model can report "they named this rule but never said
    # what it costs" honestly. A required float leaves it no way to say that
    # and it fills in 0.0 instead - which used to persist a real service at
    # $0.00 and make the pricing engine deterministically quote nothing for
    # it. The flow re-asks for a missing amount rather than storing a
    # placeholder; nothing downstream ever sees None (see _incomplete_rules).
    unit_amount_dollars: float | None = None
    unit: str = "each"


class PricingRulesDraft(BaseModel):
    rules: list[PricingRuleDraft] = Field(default_factory=list)


class EscalationDraft(BaseModel):
    """How readily this business wants its assistant to hand off to a human.

    Admins answer this question in words ("only if it's unusual", "be
    cautious, hand it over whenever you're not sure"), never in numbers, so
    ``posture`` is what the model can actually transcribe. A required bare
    float left it no way to say "they described this but gave no number" and
    it filled in 0.0 - which reads as *never escalate on low confidence*
    (supervisor compares ``confidence < threshold``), the exact opposite of
    the caution a "be cautious" answer asked for. Same failure shape as an
    unpriced pricing rule, and fixed the same way: the model reports what was
    said, ``resolve_threshold`` decides the number.
    """

    posture: Literal["rarely", "balanced", "cautious"] | None = None
    # Only set when the admin genuinely stated a number themselves; ignored
    # unless it lands in [0, 1].
    threshold: float | None = None


# Deliberately spread around the schema default (0.5) rather than reaching
# 0 or 1: a tenant that never escalates and a tenant that escalates
# everything are both misconfigurations, not postures anyone asks for.
_POSTURE_THRESHOLDS: dict[str, float] = {
    "rarely": 0.25,
    "balanced": 0.5,
    "cautious": 0.75,
}
# Mirrors the tenant_config.escalation_threshold column default (0003).
DEFAULT_ESCALATION_THRESHOLD = 0.5


def resolve_threshold(draft: EscalationDraft) -> float:
    """Turn an escalation answer into the stored threshold, in Python only.

    An explicit in-range number the admin actually gave wins; otherwise the
    posture maps to one; otherwise the column default stands. Never returns a
    fabricated 0.
    """
    if draft.threshold is not None and 0.0 <= draft.threshold <= 1.0:
        return draft.threshold
    if draft.posture is not None:
        return _POSTURE_THRESHOLDS[draft.posture]
    return DEFAULT_ESCALATION_THRESHOLD


PROMPTS: dict[str, str] = {
    "identity": (
        "In one or two sentences, what does your business do, and who are your customers?"
    ),
    "tone": (
        "How should your assistant sound when talking to customers - friendly "
        "and casual, formal and professional, something else?"
    ),
    "services": (
        "What do you offer? List your services or products, with rough prices if you have them."
    ),
    "pricing_rules": (
        "Any specific pricing rules we should know about - different rates for "
        "different tiers, rush fees, minimum charges? If not, just say so."
    ),
    "escalation_threshold": (
        "When should your assistant hand off to a human instead of answering "
        "itself - only for unusual situations ('rarely'), a middle ground "
        "('balanced'), or more cautiously whenever it isn't fully sure "
        "('cautious')?"
    ),
    "knowledge_prompt": (
        "Once you're live you can upload documents like FAQs or price sheets "
        "in the Knowledge tab to make your assistant even more accurate. "
        "Ready to review and confirm?"
    ),
}

# One re-ask for a missing price, then move on without it. Two rounds of
# "what does that cost?" is the most an onboarding conversation can spend on
# a single rule before it stops feeling like a conversation and starts
# feeling like a form that will not let you leave.
_MAX_PRICING_FOLLOWUPS = 1

_EXTRACTION_SCHEMAS: dict[str, type[BaseModel]] = {
    "identity": IdentityDraft,
    "tone": ToneDraft,
    "services": ServicesDraft,
    "pricing_rules": PricingRulesDraft,
    "escalation_threshold": EscalationDraft,
}


class OnboardingState(BaseModel):
    stage: str = STAGE_ORDER[0]
    draft: dict[str, dict[str, object]] = Field(default_factory=dict)
    # Set when a stage's answer was understood but incomplete: the flow stays
    # on that stage and asks this instead of the stock prompt, rather than
    # advancing with a half-filled draft.
    followup: str | None = None
    # How many times the current stage has already re-asked. Bounded so the
    # conversation always terminates (see _MAX_PRICING_FOLLOWUPS).
    followup_count: int = 0


def next_prompt(state: OnboardingState) -> str:
    """The assistant's next message for the current stage.

    At ``confirm`` there is nothing left to ask - the frontend shows the
    summary panel and a confirm action instead of another chat prompt.
    """
    if state.followup:
        return state.followup
    if state.stage == "confirm":
        return "Everything's captured - review the summary and confirm to go live."
    return PROMPTS[state.stage]


def _incomplete_rules(rules: list[PricingRuleDraft]) -> list[PricingRuleDraft]:
    """Rules the admin named without ever giving a usable amount.

    Non-positive is treated the same as missing: a rule that costs nothing is
    not something the pricing engine should ever compute a line from, and it
    is far more likely to be the model padding a required field than a real
    free service (genuinely free things belong in the knowledge base, not the
    price rules).
    """
    return [r for r in rules if r.unit_amount_dollars is None or r.unit_amount_dollars <= 0]


def _prior_rules_context(rules: list[PricingRuleDraft]) -> str:
    """Render the rules captured so far, to carry into a follow-up extraction.

    Each ``extract`` call sees exactly one message, so a reply to the
    follow-up ("deep cleaning is 130 a quadrant") would otherwise yield only
    the rules it mentions and drop the rest. Feeding the running set back in
    and asking for the *complete* list keeps one authoritative answer per
    turn - and, unlike merging the two results afterwards, it survives the
    model renaming a code between turns (``wisdom_teeth`` one turn,
    ``wisdom_tooth_removal`` the next), which no key-based merge can
    reconcile.
    """
    lines = [
        f"- code={r.code} label={r.label!r} unit={r.unit} amount="
        + ("MISSING" if r.unit_amount_dollars is None else f"{r.unit_amount_dollars}")
        for r in rules
    ]
    return (
        "\n\nRules captured so far from this admin:\n"
        + "\n".join(lines)
        + "\n\nThe admin is now supplying the amounts that were missing. Return the "
        "COMPLETE list of rules, reusing the codes above unchanged, with every "
        "amount filled in from what they have said. Do not drop a rule and do not "
        "invent an amount they never gave."
    )


async def advance(
    state: OnboardingState, user_input: str, provider: LLMProvider
) -> OnboardingState:
    """Extract the current stage's draft from ``user_input`` and move to the next stage.

    Raises ``ValueError`` if called at ``confirm`` - that stage has no message
    to advance from; the caller must use the confirm endpoint instead.
    """
    if state.stage == "confirm":
        raise ValueError("onboarding is already at the confirm stage")

    new_draft = dict(state.draft)
    if state.stage == "knowledge_prompt":
        # No extraction needed - any reply just acknowledges the prompt.
        pass
    else:
        schema = _EXTRACTION_SCHEMAS[state.stage]
        system_prompt = _SYSTEM_PROMPT_PREFIX + PROMPTS[state.stage]
        prior_rules: list[PricingRuleDraft] = []
        if state.stage == "pricing_rules" and state.followup:
            prior_rules = PricingRulesDraft.model_validate(state.draft["pricing_rules"]).rules
            system_prompt += _prior_rules_context(prior_rules)

        extracted = await provider.extract(
            system_prompt=system_prompt, user_input=user_input, schema=schema
        )

        if isinstance(extracted, PricingRulesDraft):
            missing = _incomplete_rules(extracted.rules)
            attempts = state.followup_count + 1
            if missing and attempts <= _MAX_PRICING_FOLLOWUPS:
                # Stay on this stage and ask for the amounts by name, keeping
                # the running draft so priced rules survive the round trip.
                named = ", ".join(f"{r.label!r}" for r in missing)
                return OnboardingState(
                    stage=state.stage,
                    draft={**new_draft, state.stage: extracted.model_dump()},
                    followup=(
                        f"I've got {named} noted as a pricing rule, but no amount "
                        "to go with it. What should each one cost? I can't store a "
                        "rule without a price - the assistant would quote it as free."
                    ),
                    followup_count=attempts,
                )
            if missing:
                # Asked and still no amount. Drop the unpriced rules rather
                # than block the admin at this stage forever or store a
                # placeholder price: the stage must terminate, and a rule
                # that never reaches the table cannot be quoted at $0. They
                # are addable with a real price in the Pricing tab.
                extracted = PricingRulesDraft(
                    rules=[r for r in extracted.rules if r not in missing]
                )

        new_draft[state.stage] = extracted.model_dump()

    next_index = STAGE_ORDER.index(state.stage) + 1
    return OnboardingState(stage=STAGE_ORDER[next_index], draft=new_draft)
