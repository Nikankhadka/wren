"""C-3: the prompt half of the money guardrail reaches every surface that
authors prose.

The deterministic gate (C-1/C-2) is the floor and the sole arbiter, so nothing
here relaxes it. What these tests protect is the *other* half of the contract:
without the instruction the model violates constantly, every violation costs a
redraft, and a redraft is latency the customer feels. A prompt line is easy to
drop in a refactor and impossible to notice missing - the gate keeps passing,
the answers just get slower and more evasive. So the rule's presence is
asserted rather than assumed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.agents.drafting import MONEY_GUIDANCE
from app.agents.spotlight import new_spotlight
from app.onboarding.agent import _EXTRACT_PROMPT, _URL_EXTRACT_PROMPT
from app.services.context_package import ContextPackage


def _package(*, fast_path: bool) -> ContextPackage:
    return ContextPackage(
        tenant_id=uuid.uuid4(),
        version=datetime.now(UTC),
        business_name="Test Co",
        profile={"business_name": "Test Co", "services": "Screen repair, $89 flat"},
        chunks=[],
        fast_path=fast_path,
    )


def test_money_rule_forbids_the_four_ways_a_figure_gets_invented() -> None:
    """Naming each one matters: a model told only "do not invent prices" still
    happily adds two menu items together, because summing does not feel like
    inventing."""
    lowered = MONEY_GUIDANCE.lower()
    assert "exact figure" in lowered
    for forbidden in ("add amounts together", "total", "round", "estimate"):
        assert forbidden in lowered
    for hedge in ("about", "around", "roughly"):
        assert hedge in lowered
    # The rule has to name the way out, or the model's only options are to
    # invent or to stonewall (C-3 US-1).
    assert "owner confirm" in lowered


def test_customer_assistant_carries_the_rule_on_both_paths() -> None:
    """Fast path or hybrid, a figure can appear in the answer either way."""
    from app.agents.agent_node import _system_prompt

    for fast_path in (True, False):
        prompt = _system_prompt(_package(fast_path=fast_path), new_spotlight())
        assert MONEY_GUIDANCE in prompt


def test_knowledge_redraft_prompt_carries_the_rule() -> None:
    """The redraft is the attempt that follows a violation - the one place the
    rule most needs to be present."""
    from app.agents.draft_node import _build_knowledge_prompt

    prompt = _build_knowledge_prompt(
        [{"content": "Screen repair is $89."}],
        violations=["'$95' does not reconcile"],
    )
    assert MONEY_GUIDANCE in prompt


def test_every_prose_route_carries_a_money_rule() -> None:
    """W-9 put all six routes behind one contract; the money half of the
    guardrail has to survive that, on the three routes that never saw tenant
    configuration before it as much as on the ones that did."""
    from app.agents.draft_node import (
        _SYSTEM_PROMPT_CONVERSATION,
        _build_quoting_prompt,
        _build_recommendation_prompt,
    )

    assert MONEY_GUIDANCE in _SYSTEM_PROMPT_CONVERSATION
    assert MONEY_GUIDANCE in _build_recommendation_prompt(
        [{"name": "Screen repair", "description": "Same day", "price_cents": 8900}], None
    )
    # Quoting carries a stricter rule than MONEY_GUIDANCE, not a weaker one: the
    # priced card beside the message is the only source of figures, so the model
    # may state none at all. Adding the general rule here would licence exactly
    # the figures this route forbids.
    quoting = _build_quoting_prompt(
        {"line_items": [{"label": "Screen repair", "quantity": 1}]}, None
    )
    assert "Do NOT state any prices, totals, or other monetary amounts" in quoting


def test_onboarding_extraction_must_copy_amounts_verbatim() -> None:
    """The interview profile is one of the gate's three allowed sources, so an
    amount the extractor tidies up becomes an amount the gate blesses forever."""
    for prompt in (_EXTRACT_PROMPT, _URL_EXTRACT_PROMPT):
        assert "exactly as" in prompt.lower()
        assert "round" in prompt.lower()
