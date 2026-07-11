"""T-006: the tenant-admin onboarding conversation (Surface-2 Copilot).

Progress is persisted in ``tenant_config.config->'onboarding'`` (a jsonb key,
merged in place so it never clobbers other ``config`` keys), so a refresh
mid-flow resumes exactly where the admin left off. Confirming writes the
captured fields into ``tenant_config``/``catalog_items``/``pricing_rules`` in
one transaction and marks the onboarding record completed; it is rejected if
called before the flow reaches the ``confirm`` stage, or a second time after
it already succeeded (no duplicate catalog/pricing rows from a double
submit).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core import auth, db
from app.ingestion.pipeline import ingest_catalog_items

if TYPE_CHECKING:
    from app.core.db import AppConnection
from app.llm.dependency import get_llm_provider
from app.llm.provider import LLMProvider
from app.onboarding.flow import (
    EscalationDraft,
    IdentityDraft,
    OnboardingState,
    PricingRulesDraft,
    ServicesDraft,
    ToneDraft,
    advance,
    next_prompt,
)

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


class OnboardingStateResponse(BaseModel):
    stage: str
    prompt: str
    draft: dict[str, dict[str, Any]]
    completed: bool


class OnboardingMessageRequest(BaseModel):
    text: str = Field(min_length=1)


class OnboardingConfirmResponse(BaseModel):
    tenant_id: UUID
    catalog_items_created: int
    pricing_rules_created: int


async def _load_record(conn: AppConnection, tenant_id: UUID) -> dict[str, Any]:
    raw = await conn.fetchval(
        "select config->'onboarding' from tenant_config where tenant_id = $1", tenant_id
    )
    parsed = json.loads(raw) if raw is not None else None
    return parsed if parsed else {"state": OnboardingState().model_dump(), "completed": False}


async def _save_record(conn: AppConnection, tenant_id: UUID, record: dict[str, Any]) -> None:
    await conn.execute(
        "update tenant_config set config = jsonb_set(config, '{onboarding}', $2::jsonb, true), "
        "updated_at = now() where tenant_id = $1",
        tenant_id,
        json.dumps(record),
    )


def _response_from_record(record: dict[str, Any]) -> OnboardingStateResponse:
    state = OnboardingState.model_validate(record["state"])
    return OnboardingStateResponse(
        stage=state.stage,
        prompt=next_prompt(state),
        draft=state.draft,
        completed=bool(record.get("completed", False)),
    )


@router.get("/state", response_model=OnboardingStateResponse)
async def get_state(
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_tenant_admin)],
) -> OnboardingStateResponse:
    async with db.tenant_context(admin.tenant_id, "tenant_admin") as conn:
        record = await _load_record(conn, admin.tenant_id)
    return _response_from_record(record)


@router.post("/message", response_model=OnboardingStateResponse)
async def post_message(
    body: OnboardingMessageRequest,
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_tenant_admin)],
    provider: Annotated[LLMProvider, Depends(get_llm_provider)],
) -> OnboardingStateResponse:
    async with db.tenant_context(admin.tenant_id, "tenant_admin") as conn:
        record = await _load_record(conn, admin.tenant_id)
        if record.get("completed", False):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="onboarding already confirmed"
            )
        state = OnboardingState.model_validate(record["state"])
        if state.stage == "confirm":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="onboarding is at the confirm stage - use POST /api/onboarding/confirm",
            )
        new_state = await advance(state, body.text, provider)
        record["state"] = new_state.model_dump()
        await _save_record(conn, admin.tenant_id, record)
    return _response_from_record(record)


def _cents(dollars: float) -> int:
    return round(dollars * 100)


@router.post("/confirm", response_model=OnboardingConfirmResponse)
async def confirm(
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_tenant_admin)],
    provider: Annotated[LLMProvider, Depends(get_llm_provider)],
) -> OnboardingConfirmResponse:
    async with db.tenant_context(admin.tenant_id, "tenant_admin") as conn:
        record = await _load_record(conn, admin.tenant_id)
        if record.get("completed", False):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="onboarding already confirmed"
            )
        state = OnboardingState.model_validate(record["state"])
        if state.stage != "confirm":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="onboarding has not reached the confirm stage yet",
            )

        identity = IdentityDraft.model_validate(state.draft["identity"])
        tone = ToneDraft.model_validate(state.draft["tone"])
        services = ServicesDraft.model_validate(state.draft["services"])
        pricing_rules = PricingRulesDraft.model_validate(state.draft["pricing_rules"])
        escalation = EscalationDraft.model_validate(state.draft["escalation_threshold"])
        threshold = max(0.0, min(1.0, escalation.threshold))

        system_prompt = (
            "You are the AI support and sales assistant for this business. "
            f"About the business: {identity.description}"
        )
        await conn.execute(
            "update tenant_config set system_prompt = $2, tone = $3, "
            "escalation_threshold = $4, updated_at = now() where tenant_id = $1",
            admin.tenant_id,
            system_prompt,
            tone.tone,
            threshold,
        )

        for item in services.items:
            price_cents = _cents(item.price_dollars) if item.price_dollars is not None else None
            await conn.execute(
                "insert into catalog_items (tenant_id, name, description, price_cents) "
                "values ($1, $2, $3, $4)",
                admin.tenant_id,
                item.name,
                item.description,
                price_cents,
            )

        for rule in pricing_rules.rules:
            await conn.execute(
                "insert into pricing_rules (tenant_id, code, label, unit_amount_cents, unit) "
                "values ($1, $2, $3, $4, $5)",
                admin.tenant_id,
                rule.code,
                rule.label,
                _cents(rule.unit_amount_dollars),
                rule.unit,
            )

        await ingest_catalog_items(conn, tenant_id=admin.tenant_id, provider=provider)

        record["completed"] = True
        await _save_record(conn, admin.tenant_id, record)

    return OnboardingConfirmResponse(
        tenant_id=admin.tenant_id,
        catalog_items_created=len(services.items),
        pricing_rules_created=len(pricing_rules.rules),
    )
