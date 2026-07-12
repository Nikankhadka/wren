"""T-028: cost/step cap + timeout unit tests.

Pure budget math and limit resolution, the timeout wrapper, the
provider-timeout wrapper, and a forced-cycle proof that the graph step cap
(LangGraph recursion_limit) actually stops a runaway loop.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from langgraph.errors import GraphRecursionError
from langgraph.graph import START, StateGraph
from typing_extensions import TypedDict

from app.core.config import get_settings
from app.core.limits import (
    DEFAULT_DAILY_COST_USD,
    DEFAULT_MAX_STEPS,
    LimitTimeout,
    TenantLimits,
    TimeLimitedProvider,
    Usage,
    budget_exceeded,
    with_timeout,
)
from app.llm.provider import ChatMessage, LLMProvider, SchemaT

# --- limit resolution -------------------------------------------------------------


def test_resolve_uses_platform_defaults_when_no_config() -> None:
    limits = TenantLimits.resolve(None, get_settings())
    assert limits.daily_cost_usd == DEFAULT_DAILY_COST_USD
    assert limits.max_steps == DEFAULT_MAX_STEPS


def test_resolve_overrides_only_the_subset_the_tenant_set() -> None:
    limits = TenantLimits.resolve(
        {"limits": {"daily_cost_usd": 1.5, "max_steps": 4}}, get_settings()
    )
    assert limits.daily_cost_usd == 1.5
    assert limits.max_steps == 4
    # untouched keys keep their defaults
    assert limits.daily_tokens == TenantLimits.resolve(None, get_settings()).daily_tokens


def test_resolve_ignores_malformed_values() -> None:
    # negative, zero, wrong-type, and boolean values all fall back to defaults
    # rather than taking the assistant offline.
    limits = TenantLimits.resolve(
        {
            "limits": {
                "daily_cost_usd": -5,
                "max_steps": "lots",
                "daily_tokens": 0,
                "llm_timeout_s": True,
            }
        },
        get_settings(),
    )
    defaults = TenantLimits.resolve(None, get_settings())
    assert limits == defaults


def test_resolve_ignores_non_dict_limits_blob() -> None:
    assert TenantLimits.resolve({"limits": "nope"}, get_settings()) == TenantLimits.resolve(
        None, get_settings()
    )


# --- budget math ------------------------------------------------------------------


def _limits(**kw: float) -> TenantLimits:
    base = {
        "daily_cost_usd": 5.0,
        "daily_tokens": 1_000_000,
        "max_steps": 8,
        "llm_timeout_s": 45.0,
        "tool_timeout_s": 15.0,
    }
    base.update(kw)
    return TenantLimits(**base)  # type: ignore[arg-type]


def test_budget_not_exceeded_under_both_ceilings() -> None:
    assert not budget_exceeded(Usage(cost_usd=4.99, tokens=999_999), _limits())


def test_budget_exceeded_on_cost() -> None:
    assert budget_exceeded(Usage(cost_usd=5.0, tokens=0), _limits())


def test_budget_exceeded_on_tokens() -> None:
    assert budget_exceeded(Usage(cost_usd=0.0, tokens=1_000_000), _limits())


# --- timeout wrapper --------------------------------------------------------------


async def test_with_timeout_returns_value_when_fast() -> None:
    async def quick() -> int:
        return 42

    assert await with_timeout(quick(), 1.0, what="quick") == 42


async def test_with_timeout_raises_limit_timeout_when_slow() -> None:
    async def slow() -> int:
        await asyncio.sleep(1.0)
        return 1

    with pytest.raises(LimitTimeout) as exc:
        await with_timeout(slow(), 0.01, what="slow op")
    assert exc.value.what == "slow op"


# --- provider timeout wrapper -----------------------------------------------------


class _SlowProvider(LLMProvider):
    async def extract(
        self, *, system_prompt: str, user_input: str, schema: type[SchemaT]
    ) -> SchemaT:
        await asyncio.sleep(1.0)
        raise AssertionError("should have timed out")

    async def chat(self, messages: list[ChatMessage]) -> str:
        await asyncio.sleep(1.0)
        return "never"

    async def chat_stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        await asyncio.sleep(1.0)
        yield "never"


class _FastProvider(LLMProvider):
    async def extract(
        self, *, system_prompt: str, user_input: str, schema: type[SchemaT]
    ) -> SchemaT:
        raise NotImplementedError

    async def chat(self, messages: list[ChatMessage]) -> str:
        return "ok"

    async def chat_stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        for token in ("a", "b", "c"):
            yield token


async def test_time_limited_provider_bounds_chat() -> None:
    provider = TimeLimitedProvider(_SlowProvider(), timeout_s=0.01)
    with pytest.raises(LimitTimeout):
        await provider.chat([{"role": "user", "content": "hi"}])


async def test_time_limited_provider_bounds_each_stream_token() -> None:
    provider = TimeLimitedProvider(_SlowProvider(), timeout_s=0.01)
    with pytest.raises(LimitTimeout):
        async for _ in provider.chat_stream([{"role": "user", "content": "hi"}]):
            pass


async def test_time_limited_provider_passes_through_fast_calls() -> None:
    provider = TimeLimitedProvider(_FastProvider(), timeout_s=1.0)
    assert await provider.chat([{"role": "user", "content": "hi"}]) == "ok"
    tokens = [t async for t in provider.chat_stream([{"role": "user", "content": "hi"}])]
    assert tokens == ["a", "b", "c"]


# --- forced-cycle step-cap proof --------------------------------------------------


class _PingPongState(TypedDict):
    count: int


async def test_step_cap_stops_a_runaway_cycle() -> None:
    """A graph that ping-pongs forever must raise GraphRecursionError at the
    step cap rather than loop until the process dies - this is the loop
    protection the real graph relies on for its retry/route edges."""

    async def ping(state: _PingPongState) -> _PingPongState:
        return {"count": state["count"] + 1}

    graph = StateGraph(_PingPongState)
    graph.add_node("ping", ping)
    graph.add_node("pong", ping)
    graph.add_edge(START, "ping")
    graph.add_edge("ping", "pong")
    graph.add_edge("pong", "ping")  # deliberate cycle, no exit
    compiled = graph.compile()

    with pytest.raises(GraphRecursionError):
        await compiled.ainvoke({"count": 0}, config={"recursion_limit": DEFAULT_MAX_STEPS})
