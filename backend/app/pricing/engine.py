"""T-016: the deterministic pricing engine.

NO LLM IMPORTS ANYWHERE IN THIS MODULE, full stop. This is the one hard-rule
enforcement point (Wren_AGENTS.md hard rule 1 / this phase's shared
contracts): agents select ``rule_code``/``catalog_item_id`` + quantity,
never a number - this module reads the tenant's pricing_rules/catalog_items
fresh from the DB and computes every cent. "Pure function" here means
deterministic given DB state, not side-effect-free - it still needs a live
read, since agent-selected data can't be trusted stale.

An unknown/inactive code or id, an out-of-bounds quantity, or a quantity
below a rule's ``min_qty`` all raise ``SelectionError`` - the caller (the
Quoting Agent, T-017) re-selects; the engine never guesses or substitutes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID

if TYPE_CHECKING:
    from app.core.db import AppConnection

MIN_QUANTITY = 1
MAX_QUANTITY = 999


class SelectionError(Exception):
    """An invalid selection - unknown/inactive code or id, quantity out of
    bounds, or below a rule's min_qty. The caller must re-select."""


@dataclass(frozen=True)
class Selection:
    kind: Literal["rule", "item"]
    code_or_id: str
    quantity: int


@dataclass(frozen=True)
class LineItem:
    kind: Literal["rule", "item"]
    code: str
    label: str
    quantity: int
    unit_amount_cents: int
    line_total_cents: int

    def to_dict(self) -> dict[str, Any]:
        key = "code" if self.kind == "rule" else "item_id"
        return {
            "kind": self.kind,
            key: self.code,
            "label": self.label,
            "quantity": self.quantity,
            "unit_amount_cents": self.unit_amount_cents,
            "line_total_cents": self.line_total_cents,
        }


@dataclass(frozen=True)
class EngineQuote:
    line_items: list[LineItem]
    subtotal_cents: int
    tax_cents: int
    total_cents: int


def _check_quantity_bounds(quantity: int) -> None:
    if not (MIN_QUANTITY <= quantity <= MAX_QUANTITY):
        raise SelectionError(
            f"quantity {quantity} is out of bounds ({MIN_QUANTITY}..{MAX_QUANTITY})"
        )


async def _price_rule(conn: AppConnection, tenant_id: UUID, selection: Selection) -> LineItem:
    row = await conn.fetchrow(
        "select code, label, unit_amount_cents, conditions from pricing_rules "
        "where tenant_id = $1 and code = $2 and active",
        tenant_id,
        selection.code_or_id,
    )
    if row is None:
        raise SelectionError(f"unknown or inactive pricing rule: {selection.code_or_id!r}")

    conditions = json.loads(row["conditions"])
    min_qty = conditions.get("min_qty")
    if min_qty is not None and selection.quantity < min_qty:
        raise SelectionError(
            f"quantity {selection.quantity} is below rule {selection.code_or_id!r}'s "
            f"minimum of {min_qty}"
        )

    return LineItem(
        kind="rule",
        code=row["code"],
        label=row["label"],
        quantity=selection.quantity,
        unit_amount_cents=row["unit_amount_cents"],
        line_total_cents=row["unit_amount_cents"] * selection.quantity,
    )


async def _price_item(conn: AppConnection, tenant_id: UUID, selection: Selection) -> LineItem:
    try:
        item_id = UUID(selection.code_or_id)
    except ValueError as exc:
        raise SelectionError(f"malformed catalog item id: {selection.code_or_id!r}") from exc

    row = await conn.fetchrow(
        "select id, name, price_cents from catalog_items "
        "where tenant_id = $1 and id = $2 and active",
        tenant_id,
        item_id,
    )
    if row is None:
        raise SelectionError(f"unknown or inactive catalog item: {selection.code_or_id!r}")
    if row["price_cents"] is None:
        raise SelectionError(
            f"catalog item {selection.code_or_id!r} has no direct price "
            "(priced via rules instead - select the rule, not the item)"
        )

    return LineItem(
        kind="item",
        code=str(row["id"]),
        label=row["name"],
        quantity=selection.quantity,
        unit_amount_cents=row["price_cents"],
        line_total_cents=row["price_cents"] * selection.quantity,
    )


async def _tax_rate_bps(conn: AppConnection, tenant_id: UUID) -> int:
    raw = await conn.fetchval("select config from tenant_config where tenant_id = $1", tenant_id)
    if raw is None:
        return 0
    config = json.loads(raw)
    rate_bps = config.get("tax", {}).get("rate_bps", 0)
    return int(rate_bps)


async def compute_quote(
    conn: AppConnection, tenant_id: UUID, selections: list[Selection]
) -> EngineQuote:
    if not selections:
        raise SelectionError("no selections provided")

    line_items: list[LineItem] = []
    for selection in selections:
        _check_quantity_bounds(selection.quantity)
        if selection.kind == "rule":
            line_items.append(await _price_rule(conn, tenant_id, selection))
        else:
            line_items.append(await _price_item(conn, tenant_id, selection))

    subtotal_cents = sum(item.line_total_cents for item in line_items)
    rate_bps = await _tax_rate_bps(conn, tenant_id)
    tax_cents = subtotal_cents * rate_bps // 10000
    total_cents = subtotal_cents + tax_cents

    return EngineQuote(
        line_items=line_items,
        subtotal_cents=subtotal_cents,
        tax_cents=tax_cents,
        total_cents=total_cents,
    )
