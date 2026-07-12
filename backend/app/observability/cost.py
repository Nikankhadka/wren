"""T-030: LLM cost accounting.

Every LLM call the app makes reports its token usage through a per-turn sink
(a contextvar), so the singleton provider stays stateless and thread-safe
while the caller that knows the tenant/conversation (chat.py) collects usage
for the whole turn and writes it to ``cost_logs`` once.

USD is computed deterministically from a per-model price table (dollars per
million tokens). The free-first default models cost $0 - the machinery is
correct regardless, and a hosted model just needs a price-table entry.
Aggregation queries back the per-tenant/day budget (T-028) and the
per-conversation cost shown in the Surface-2 trace (T-031/T-034).

The provider abstraction still returns only its parsed/text result - usage is
a side channel via :func:`report_usage`, so no call site changed and a
provider that can't report usage (a test fake) simply reports nothing.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.core import db


@dataclass(frozen=True)
class TokenUsage:
    model: str
    input_tokens: int
    output_tokens: int


# Dollars per 1,000,000 tokens: (input, output). Unknown models cost $0 (the
# free-first default) - add an entry to price a hosted model. Keys match the
# model/deployment string the provider reports.
PRICE_TABLE: dict[str, tuple[Decimal, Decimal]] = {
    # Reference paid models (Azure/OpenAI list prices) so a swap prices itself.
    "gpt-4o-mini": (Decimal("0.15"), Decimal("0.60")),
    "text-embedding-3-small": (Decimal("0.02"), Decimal("0")),
}


def compute_cost_usd(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    """Deterministic USD for one call. Unknown/free models -> 0."""
    input_price, output_price = PRICE_TABLE.get(model, (Decimal("0"), Decimal("0")))
    cost = (Decimal(input_tokens) * input_price + Decimal(output_tokens) * output_price) / Decimal(
        1_000_000
    )
    # cost_logs.cost_usd is numeric(12,6) - quantize to match, so the stored
    # value and any reconciliation math agree exactly.
    return cost.quantize(Decimal("0.000001"))


# --- per-turn usage sink --------------------------------------------------------

_usage_sink: ContextVar[list[TokenUsage] | None] = ContextVar("_usage_sink", default=None)


@contextmanager
def collect_usage() -> Iterator[list[TokenUsage]]:
    """Activate a fresh usage sink for the duration of a turn. Every
    :func:`report_usage` call inside appends to the yielded list. Nesting
    replaces the sink and restores the previous one on exit (contextvars are
    task-local, so concurrent turns never share a sink)."""
    sink: list[TokenUsage] = []
    token = _usage_sink.set(sink)
    try:
        yield sink
    finally:
        _usage_sink.reset(token)


def report_usage(model: str, input_tokens: int, output_tokens: int) -> None:
    """Called by a provider after a completion. No active sink (e.g. an eval
    or a test not collecting cost) -> silently dropped."""
    sink = _usage_sink.get()
    if sink is not None:
        sink.append(TokenUsage(model=model, input_tokens=input_tokens, output_tokens=output_tokens))


# --- persistence + aggregation --------------------------------------------------


async def record_costs(
    conn: db.AppConnection,
    tenant_id: UUID,
    conversation_id: UUID,
    usages: list[TokenUsage],
) -> Decimal:
    """Write one cost_logs row per LLM call of a turn; return the turn's total
    USD. ``conn`` must already be in the tenant's context (RLS scopes the
    write). Empty usage list writes nothing."""
    total = Decimal("0")
    for usage in usages:
        cost = compute_cost_usd(usage.model, usage.input_tokens, usage.output_tokens)
        total += cost
        await conn.execute(
            "insert into cost_logs "
            "(tenant_id, conversation_id, model, input_tokens, output_tokens, cost_usd) "
            "values ($1, $2, $3, $4, $5, $6)",
            tenant_id,
            conversation_id,
            usage.model,
            usage.input_tokens,
            usage.output_tokens,
            cost,
        )
    return total


async def cost_for_conversation(conn: db.AppConnection, conversation_id: UUID) -> Decimal:
    value = await conn.fetchval(
        "select coalesce(sum(cost_usd), 0) from cost_logs where conversation_id = $1",
        conversation_id,
    )
    return Decimal(str(value))


async def cost_for_tenant_day(conn: db.AppConnection, tenant_id: UUID) -> Decimal:
    value = await conn.fetchval(
        "select coalesce(sum(cost_usd), 0) from cost_logs "
        "where tenant_id = $1 and created_at >= date_trunc('day', now())",
        tenant_id,
    )
    return Decimal(str(value))
