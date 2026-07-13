"""T-031: Surface 2's Pricing tab - pricing_rules inline editing + a
read-only catalog_items list.

Currency conversion happens ONLY at this API boundary: the client sends a
decimal dollar string/number, this module converts it to integer cents
server-side (never trusting a client-supplied cents value directly). This is
the deterministic-pricing hard rule applied to admin-authored config, same
reasoning as T-006's onboarding price extraction - an admin is the source of
the number, arithmetic on it still never happens inside an LLM call, and here
not even inside the client.

Editing a rule's amount only affects quotes computed AFTER the edit - a
`sent` quote's line_items/totals are already persisted verbatim and the
quotes_immutable trigger (T-002/T-016) physically prevents them from ever
changing.
"""

from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator

from app.core import auth, db

router = APIRouter(prefix="/api/pricing", tags=["pricing"])

_MAX_DOLLARS = Decimal("1000000")


class PricingRuleResponse(BaseModel):
    id: UUID
    code: str
    label: str
    unit_amount_cents: int
    unit: str
    active: bool
    updated_at: datetime


class CatalogItemResponse(BaseModel):
    id: UUID
    name: str
    description: str
    price_cents: int | None
    active: bool
    updated_at: datetime


class PricingRuleUpdate(BaseModel):
    code: str | None = None
    label: str | None = None
    unit_amount_dollars: Decimal | None = None
    unit: str | None = None
    active: bool | None = None

    @field_validator("code", "label", "unit")
    @classmethod
    def _reject_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("unit_amount_dollars", mode="before")
    @classmethod
    def _parse_dollars(cls, value: object) -> Decimal | None:
        if value is None:
            return None
        try:
            amount = Decimal(str(value))
        except InvalidOperation as exc:
            raise ValueError("not a valid decimal amount") from exc
        if not amount.is_finite():
            raise ValueError("amount must be finite")
        if amount < 0:
            raise ValueError("amount must not be negative")
        if amount > _MAX_DOLLARS:
            raise ValueError(f"amount must not exceed {_MAX_DOLLARS}")
        # At most 2 decimal places - reject e.g. 1.999 rather than silently
        # rounding an admin-authored price to something they didn't type.
        if amount != amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP):
            raise ValueError("amount must have at most 2 decimal places")
        return amount

    def cents(self) -> int | None:
        if self.unit_amount_dollars is None:
            return None
        return int((self.unit_amount_dollars * 100).to_integral_value(rounding=ROUND_HALF_UP))


@router.get("/rules", response_model=list[PricingRuleResponse])
async def list_pricing_rules(
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_tenant_admin)],
) -> list[PricingRuleResponse]:
    async with db.tenant_context(admin.tenant_id, "tenant_admin") as conn:
        rows = await conn.fetch(
            "select id, code, label, unit_amount_cents, unit, active, updated_at "
            "from pricing_rules where tenant_id = $1 order by code",
            admin.tenant_id,
        )
    return [PricingRuleResponse(**dict(row)) for row in rows]


@router.patch("/rules/{rule_id}", response_model=PricingRuleResponse)
async def update_pricing_rule(
    rule_id: UUID,
    body: PricingRuleUpdate,
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_tenant_admin)],
) -> PricingRuleResponse:
    updates = {
        "code": body.code,
        "label": body.label,
        "unit_amount_cents": body.cents(),
        "unit": body.unit,
        "active": body.active,
    }
    updates = {key: value for key, value in updates.items() if value is not None}
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="no fields to update"
        )

    set_clause = ", ".join(f"{key} = ${i + 3}" for i, key in enumerate(updates))
    async with db.tenant_context(admin.tenant_id, "tenant_admin") as conn:
        try:
            row = await conn.fetchrow(
                f"update pricing_rules set {set_clause} "  # noqa: S608 - keys are our own fixed whitelist
                "where tenant_id = $1 and id = $2 "
                "returning id, code, label, unit_amount_cents, unit, active, updated_at",
                admin.tenant_id,
                rule_id,
                *updates.values(),
            )
        except asyncpg.UniqueViolationError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"a rule with code {updates.get('code')!r} already exists",
            ) from exc
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="pricing rule not found")
    return PricingRuleResponse(**dict(row))


@router.get("/catalog", response_model=list[CatalogItemResponse])
async def list_catalog_items(
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_tenant_admin)],
) -> list[CatalogItemResponse]:
    async with db.tenant_context(admin.tenant_id, "tenant_admin") as conn:
        rows = await conn.fetch(
            "select id, name, description, price_cents, active, updated_at "
            "from catalog_items where tenant_id = $1 order by name",
            admin.tenant_id,
        )
    return [CatalogItemResponse(**dict(row)) for row in rows]
