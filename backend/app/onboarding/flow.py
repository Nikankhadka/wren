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
    unit_amount_dollars: float
    unit: str = "each"


class PricingRulesDraft(BaseModel):
    rules: list[PricingRuleDraft] = Field(default_factory=list)


class EscalationDraft(BaseModel):
    threshold: float


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
        "itself - only for unusual situations, or more cautiously whenever "
        "it isn't fully sure?"
    ),
    "knowledge_prompt": (
        "Once you're live you can upload documents like FAQs or price sheets "
        "in the Knowledge tab to make your assistant even more accurate. "
        "Ready to review and confirm?"
    ),
}

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


def next_prompt(state: OnboardingState) -> str:
    """The assistant's next message for the current stage.

    At ``confirm`` there is nothing left to ask - the frontend shows the
    summary panel and a confirm action instead of another chat prompt.
    """
    if state.stage == "confirm":
        return "Everything's captured - review the summary and confirm to go live."
    return PROMPTS[state.stage]


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
        extracted = await provider.extract(
            system_prompt=_SYSTEM_PROMPT_PREFIX + PROMPTS[state.stage],
            user_input=user_input,
            schema=schema,
        )
        new_draft[state.stage] = extracted.model_dump()

    next_index = STAGE_ORDER.index(state.stage) + 1
    return OnboardingState(stage=STAGE_ORDER[next_index], draft=new_draft)
