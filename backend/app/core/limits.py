"""T-028: per-tenant cost/step caps and per-call timeouts.

Three protections, all graceful-by-design - a tenant hitting a limit gets a
polite "temporarily unavailable" handoff, never a stack trace:

1. **Daily budget** - a per-tenant cost and token ceiling for the current UTC
   day, read from ``tenant_config.config.limits`` with platform defaults from
   the environment. Checked before a turn runs by summing today's ``cost_logs``
   (cached briefly so a burst of turns doesn't hammer the aggregate). Over
   budget routes to a budget escalation instead of invoking the graph.
2. **Step cap** - a ceiling on graph node executions per turn (LangGraph's
   ``recursion_limit``), so a pathological retry/route cycle can't spin
   forever. Exceeding it is caught and turned into the same graceful handoff.
3. **Timeouts** - a wrapper (:func:`with_timeout`) bounds any single LLM call
   or tool call; the provider handed to the graph is wrapped so every
   ``extract``/``chat``/``chat_stream`` is time-bounded centrally.

Budget math is pure and unit-tested; the cache is process-local and
clearable (tests reset it). cost_logs are not written until T-030, so today's
usage is genuinely 0 for now - the machinery is correct and exercised, it
just has nothing to sum yet.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Awaitable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.core import db
from app.core.config import Settings
from app.llm.provider import ChatMessage, LLMProvider, SchemaT

# Platform defaults - a tenant's config.limits overrides any subset of these.
DEFAULT_DAILY_COST_USD = 5.0
DEFAULT_DAILY_TOKENS = 2_000_000
DEFAULT_MAX_STEPS = 8
DEFAULT_LLM_TIMEOUT_S = 45.0
DEFAULT_TOOL_TIMEOUT_S = 15.0

# How long a summed-usage reading stays cached per tenant. Short enough that a
# tenant crossing its cap is stopped within seconds, long enough that a burst
# of concurrent turns doesn't each re-run the aggregate.
_USAGE_CACHE_TTL_S = 10.0

BUDGET_ESCALATION_REASON = "budget"
STEP_CAP_ESCALATION_REASON = "step_cap"

BUDGET_UNAVAILABLE_MESSAGE = (
    "We're unable to answer automatically right now, so I'm passing this to a "
    "human who'll follow up with you. Thanks for your patience."
)


class LimitTimeout(Exception):
    """A single LLM or tool call exceeded its time budget. Carries what timed
    out so the caller can escalate gracefully rather than surface a raw
    asyncio.TimeoutError."""

    def __init__(self, what: str, seconds: float) -> None:
        super().__init__(f"{what} exceeded its {seconds:.0f}s time budget")
        self.what = what
        self.seconds = seconds


@dataclass(frozen=True)
class TenantLimits:
    daily_cost_usd: float
    daily_tokens: int
    max_steps: int
    llm_timeout_s: float
    tool_timeout_s: float

    @classmethod
    def resolve(cls, config: dict[str, Any] | None, settings: Settings) -> TenantLimits:
        """Platform defaults overlaid with whatever subset the tenant set in
        ``config.limits``. Unknown or malformed values fall back to the
        default rather than raising - a bad limits blob must never take a
        tenant's assistant offline."""
        limits = {}
        if config and isinstance(config.get("limits"), dict):
            limits = config["limits"]
        return cls(
            daily_cost_usd=_num(limits.get("daily_cost_usd"), DEFAULT_DAILY_COST_USD),
            daily_tokens=int(_num(limits.get("daily_tokens"), DEFAULT_DAILY_TOKENS)),
            max_steps=int(_num(limits.get("max_steps"), DEFAULT_MAX_STEPS)),
            llm_timeout_s=_num(limits.get("llm_timeout_s"), DEFAULT_LLM_TIMEOUT_S),
            tool_timeout_s=_num(limits.get("tool_timeout_s"), DEFAULT_TOOL_TIMEOUT_S),
        )


def _num(value: Any, default: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    if value <= 0:
        return default
    return float(value)


@dataclass(frozen=True)
class Usage:
    cost_usd: float
    tokens: int


def budget_exceeded(usage: Usage, limits: TenantLimits) -> bool:
    """Pure predicate: has this tenant met or passed either ceiling today?"""
    return usage.cost_usd >= limits.daily_cost_usd or usage.tokens >= limits.daily_tokens


# --- cached usage lookup --------------------------------------------------------

_usage_cache: dict[UUID, tuple[float, Usage]] = {}


def clear_usage_cache() -> None:
    """Test hook - drop all cached usage so a test's seeded cost_logs are read
    fresh."""
    _usage_cache.clear()


async def current_usage(conn: db.AppConnection, tenant_id: UUID) -> Usage:
    """Today's (UTC) summed cost and tokens for a tenant, cached briefly. The
    connection must already be inside the tenant's context (RLS scopes the
    sum to this tenant)."""
    now = time.monotonic()
    cached = _usage_cache.get(tenant_id)
    if cached is not None and now - cached[0] < _USAGE_CACHE_TTL_S:
        return cached[1]

    row = await conn.fetchrow(
        "select coalesce(sum(cost_usd), 0) as cost, "
        "coalesce(sum(input_tokens + output_tokens), 0) as tokens "
        "from cost_logs where tenant_id = $1 and created_at >= date_trunc('day', now())",
        tenant_id,
    )
    # A coalesced aggregate always returns exactly one row - the None guard is
    # only to satisfy the Record | None static type.
    usage = Usage(
        cost_usd=float(row["cost"]) if row else 0.0,
        tokens=int(row["tokens"]) if row else 0,
    )
    _usage_cache[tenant_id] = (now, usage)
    return usage


async def tenant_over_budget(conn: db.AppConnection, tenant_id: UUID, limits: TenantLimits) -> bool:
    return budget_exceeded(await current_usage(conn, tenant_id), limits)


# --- timeouts -------------------------------------------------------------------


async def with_timeout[T](coro: Awaitable[T], seconds: float, *, what: str) -> T:
    """Await ``coro`` but raise :class:`LimitTimeout` (not a bare
    asyncio.TimeoutError) if it overruns, so callers can escalate gracefully."""
    import asyncio

    try:
        return await asyncio.wait_for(coro, timeout=seconds)
    except TimeoutError as error:
        raise LimitTimeout(what, seconds) from error


class TimeLimitedProvider(LLMProvider):
    """Wraps a real provider so every call is time-bounded by the tenant's
    ``llm_timeout_s`` - one place, so no node has to remember to wrap its own
    LLM calls. A streamed call is bounded on the time-to-first-token and on
    each subsequent token gap (a stalled stream is as bad as a stalled call)."""

    def __init__(self, inner: LLMProvider, timeout_s: float) -> None:
        self._inner = inner
        self._timeout_s = timeout_s

    async def extract(
        self, *, system_prompt: str, user_input: str, schema: type[SchemaT]
    ) -> SchemaT:
        return await with_timeout(
            self._inner.extract(system_prompt=system_prompt, user_input=user_input, schema=schema),
            self._timeout_s,
            what="LLM extract",
        )

    async def chat(self, messages: list[ChatMessage]) -> str:
        return await with_timeout(self._inner.chat(messages), self._timeout_s, what="LLM chat")

    async def chat_stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        stream = self._inner.chat_stream(messages)
        while True:
            try:
                delta = await with_timeout(
                    stream.__anext__(), self._timeout_s, what="LLM chat_stream"
                )
            except StopAsyncIteration:
                return
            yield delta
