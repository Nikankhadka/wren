"""T-019: agent tools that aren't specialist nodes in their own right.

``lookup_order_or_ticket`` never raises into the model - an unknown ref_code
or a wrong-tenant lookup both come back as a typed not-found result, never
an exception. ``kind``/``status`` are tenant-defined free-text data (the
schema's own comment: "tenant-defined vocabulary, stored as data") - this
module never branches on their values, only passes them through verbatim
(domain-agnostic hard rule).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from app.core.db import AppConnection


@dataclass(frozen=True)
class OrderLookup:
    found: bool
    ref_code: str
    kind: str | None = None
    status: str | None = None
    customer_ref: str | None = None
    details: dict[str, Any] | None = None
    updated_at: datetime | None = None

    @classmethod
    def not_found(cls, ref_code: str) -> OrderLookup:
        return cls(found=False, ref_code=ref_code)


async def lookup_order_or_ticket(
    conn: AppConnection,
    tenant_id: UUID,
    ref_code: str,
    customer_ref: str | None = None,
) -> OrderLookup:
    """Case-insensitive match on ``ref_code``, explicitly scoped to
    ``tenant_id`` on top of RLS (codebase convention). A real ref_code
    belonging to a different tenant simply matches zero rows here - not
    found by construction, never a leak.

    An empty/blank ``customer_ref`` is treated as "not given", not as a
    literal empty-string filter - a structured-output model is prone to
    returning ``""`` instead of omitting an optional field, and filtering on
    a literal empty string would spuriously not-find a real order whose
    stored customer_ref is NULL or non-empty."""
    if customer_ref is not None and customer_ref.strip():
        row = await conn.fetchrow(
            "select ref_code, kind, status, customer_ref, details, updated_at "
            "from orders where tenant_id = $1 and upper(ref_code) = upper($2) "
            "and customer_ref = $3",
            tenant_id,
            ref_code,
            customer_ref,
        )
    else:
        row = await conn.fetchrow(
            "select ref_code, kind, status, customer_ref, details, updated_at "
            "from orders where tenant_id = $1 and upper(ref_code) = upper($2)",
            tenant_id,
            ref_code,
        )

    if row is None:
        return OrderLookup.not_found(ref_code)

    return OrderLookup(
        found=True,
        ref_code=row["ref_code"],
        kind=row["kind"],
        status=row["status"],
        customer_ref=row["customer_ref"],
        details=json.loads(row["details"]),
        updated_at=row["updated_at"],
    )
