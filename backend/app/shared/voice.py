"""W-9 US-7: one vocabulary for how a tenant's public assistant sounds.

Voice is expression only - warmth, formality, pacing, word choice. It never
changes a fact, a price, a policy, a tool, the assistant's identity, or an
escalation rule; that half is the code-owned contract in
``app/agents/contract.py``, and the split is the whole point of the ticket.

The keys live here rather than beside either reader because three packages need
them at once: onboarding writes them (the voice beat), services carries them (the
context package), and agents renders them (the contract). The import contracts in
``backend/pyproject.toml`` forbid ``app.services`` from importing ``app.agents``,
and duplicating the vocabulary in two places is how the two would drift.
``app.shared`` is a source module in no contract, so all three can import it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# The four voices the owner chooses between. A fixed vocabulary, not free prose:
# an expression choice that can be typed without bound is a second system prompt.
VOICE_PRESETS: tuple[str, ...] = ("warm_casual", "clear_professional", "direct_concise")
CUSTOM_VOICE = "custom"
DEFAULT_VOICE_PRESET = "warm_casual"
# The owner's own description of the voice, bounded so it stays a description.
CUSTOM_VOICE_MAX = 300

# One line of expression guidance per preset, sitting beside the keys it maps
# from so a new preset cannot be added without saying how it sounds.
_PRESET_GUIDANCE: dict[str, str] = {
    "warm_casual": "Warm and casual - friendly, everyday words, contractions are fine.",
    "clear_professional": "Clear and professional - plain, courteous, no slang.",
    "direct_concise": "Direct and concise - short sentences, no filler.",
}


@dataclass(frozen=True)
class CustomerVoice:
    """The structured voice stored at ``config->customer_voice``."""

    preset: str = DEFAULT_VOICE_PRESET
    custom_style: str = ""

    def guidance(self) -> str:
        """The single line the contract shows the model, always bounded."""
        if self.preset == CUSTOM_VOICE:
            return self.custom_style.strip()[:CUSTOM_VOICE_MAX]
        return _PRESET_GUIDANCE.get(self.preset, _PRESET_GUIDANCE[DEFAULT_VOICE_PRESET])


def voice_from_config(config: Any) -> CustomerVoice:
    """Read a voice out of a tenant's ``config`` jsonb, defaulting on anything odd.

    An unknown preset, a ``custom`` with nothing described, or no voice at all
    all resolve to the default rather than reaching the prompt as written: this
    value is the one piece of tenant data that lands inside the contract's own
    render, so it is normalized here rather than trusted there.
    """
    raw = config.get("customer_voice") if isinstance(config, dict) else None
    if not isinstance(raw, dict):
        return CustomerVoice()
    preset = str(raw.get("preset") or "").strip() or DEFAULT_VOICE_PRESET
    style = str(raw.get("custom_style") or "").strip()[:CUSTOM_VOICE_MAX]
    if preset == CUSTOM_VOICE:
        return CustomerVoice(preset=CUSTOM_VOICE, custom_style=style) if style else CustomerVoice()
    if preset not in VOICE_PRESETS:
        return CustomerVoice()
    return CustomerVoice(preset=preset)
