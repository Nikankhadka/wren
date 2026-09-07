"""O-1: onboarding tools - a single ``save_profile`` merge helper."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, Field

from app.onboarding import beats
from app.onboarding.flow import ProfileDraft

# W-9: the voice fields are server-owned. They are written only by the voice
# beat's own selection (`beats.apply_selection`) and are left out of the
# extraction prompt's field list, so a model that names one anyway still cannot
# get it into the draft.
SERVER_OWNED_FIELDS = ("customer_voice_preset", "customer_voice_custom_style")

_PROFILE_FIELDS = tuple(
    field for field in ProfileDraft.model_fields if field not in SERVER_OWNED_FIELDS
)


class ToolResult(BaseModel):
    ok: bool = True
    message: str = Field(default="")
    missing: list[str] = Field(default_factory=list)


def save_profile(draft: dict[str, Any], args: ProfileDraft) -> dict[str, Any]:
    """Merge any non-empty profile field into the flat draft."""
    for field in _PROFILE_FIELDS:
        value = getattr(args, field)
        if field == "abn" and value:
            stated = value.strip().lower()
            if stated == beats.NO_ABN:
                value = beats.NO_ABN
            else:
                digits = "".join(char for char in value if char.isdigit())
                value = digits if len(digits) == 11 else ""
        if value:
            draft[field] = value
    return draft


def _check_completeness(draft: dict[str, Any], skipped: Sequence[str] = ()) -> list[str]:
    return beats.check_completeness(draft, skipped)


def request_finalize(draft: dict[str, Any], skipped: Sequence[str] = ()) -> ToolResult:
    missing = _check_completeness(draft, skipped)
    if missing:
        return ToolResult(ok=False, missing=missing)
    return ToolResult(ok=True, message="All required fields complete.")
