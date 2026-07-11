"""T-006: onboarding state machine unit tests, with a stubbed LLMProvider.

No network, no Azure credentials needed - `advance` only ever calls
`LLMProvider.extract`, so a fake that returns canned instances proves stage
advance, resume-shaped state, and cents conversion (tested at the API layer,
see test_onboarding_api.py) without touching a real model.
"""

from __future__ import annotations

from typing import cast

import pytest
from pydantic import BaseModel

from app.llm.provider import SchemaT
from app.onboarding.flow import (
    STAGE_ORDER,
    EscalationDraft,
    IdentityDraft,
    OnboardingState,
    PricingRulesDraft,
    ServicesDraft,
    ToneDraft,
    advance,
    next_prompt,
)
from tests.fakes import BaseFakeProvider


class FakeProvider(BaseFakeProvider):
    """Returns a fixed instance per schema, ignoring the actual prompt text."""

    def __init__(self, responses: dict[type[BaseModel], BaseModel]) -> None:
        self._responses = responses

    async def extract(
        self, *, system_prompt: str, user_input: str, schema: type[SchemaT]
    ) -> SchemaT:
        response = self._responses[schema]
        assert isinstance(response, schema)
        return response


FAKE_RESPONSES: dict[type[BaseModel], BaseModel] = {
    IdentityDraft: IdentityDraft(description="A neighborhood phone repair shop."),
    ToneDraft: ToneDraft(tone="friendly"),
    ServicesDraft: ServicesDraft.model_validate(
        {
            "items": [
                {
                    "name": "Screen repair",
                    "description": "Cracked screen replacement",
                    "price_dollars": 89.0,
                }
            ]
        }
    ),
    PricingRulesDraft: PricingRulesDraft.model_validate(
        {
            "rules": [
                {
                    "code": "rush-fee",
                    "label": "Rush service",
                    "unit_amount_dollars": 25.0,
                    "unit": "flat",
                }
            ]
        }
    ),
    EscalationDraft: EscalationDraft(threshold=0.6),
}


async def test_advance_walks_every_extraction_stage_in_order() -> None:
    provider = FakeProvider(FAKE_RESPONSES)
    state = OnboardingState()

    assert state.stage == "identity"
    state = await advance(state, "we fix phones", provider)
    assert state.stage == "tone"
    assert state.draft["identity"]["description"] == "A neighborhood phone repair shop."

    state = await advance(state, "keep it friendly", provider)
    assert state.stage == "services"

    state = await advance(state, "screen repairs for $89", provider)
    assert state.stage == "pricing_rules"
    items = cast("list[dict[str, object]]", state.draft["services"]["items"])
    assert items[0]["name"] == "Screen repair"

    state = await advance(state, "rush fee is $25", provider)
    assert state.stage == "escalation_threshold"

    state = await advance(state, "escalate when unsure", provider)
    assert state.stage == "knowledge_prompt"

    state = await advance(state, "ready", provider)
    assert state.stage == "confirm"
    # knowledge_prompt makes no extraction call, so it left no draft entry.
    assert "knowledge_prompt" not in state.draft


async def test_advance_at_confirm_raises() -> None:
    provider = FakeProvider(FAKE_RESPONSES)
    state = OnboardingState(stage="confirm")
    with pytest.raises(ValueError, match="already at the confirm stage"):
        await advance(state, "anything", provider)


async def test_state_round_trips_through_model_dump_and_validate() -> None:
    """Draft persists as plain dicts (jsonb-shaped), the resume contract."""
    provider = FakeProvider(FAKE_RESPONSES)
    state = await advance(OnboardingState(), "we fix phones", provider)

    dumped = state.model_dump()
    resumed = OnboardingState.model_validate(dumped)
    assert resumed == state


def test_next_prompt_matches_stage_and_confirm_has_no_question() -> None:
    for stage in STAGE_ORDER[:-1]:
        state = OnboardingState(stage=stage)
        assert next_prompt(state)  # non-empty for every real stage

    confirm_state = OnboardingState(stage="confirm")
    assert "confirm" in next_prompt(confirm_state).lower()
