"""T-030: agent-turn tracing.

One trace per customer turn, with nested spans for the supervisor route, each
specialist node, retrieval, tool calls, the pricing engine, and inspection -
span attributes carrying tenant_id, conversation_id, model, and tokens.

Free-first: tracing is opt-in. With no ``LANGFUSE_*`` keys the tracer is a
no-op with zero overhead and zero external calls, so the default stack traces
nothing and depends on nothing. When keys are present the same interface is
backed by Langfuse (added by the founder alongside the ``langfuse`` SDK) - the
call sites never change, only ``get_tracer`` returns a live backend.

The interface is deliberately tiny (a turn context manager yielding a span
factory) so instrumentation reads the same whether or not a backend is live:

    tracer = get_tracer(settings)
    with tracer.turn(tenant_id=..., conversation_id=...) as turn:
        with turn.span("supervisor", route="quoting"):
            ...
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Protocol
from uuid import UUID

from app.core.config import Settings


class Span(Protocol):
    def set(self, **attributes: Any) -> None: ...


class Turn(Protocol):
    @contextmanager
    def span(self, name: str, **attributes: Any) -> Iterator[Span]: ...


class Tracer(Protocol):
    @contextmanager
    def turn(
        self, *, tenant_id: UUID, conversation_id: UUID, **attributes: Any
    ) -> Iterator[Turn]: ...


# --- no-op backend (the default) -------------------------------------------------


class _NoOpSpan:
    def set(self, **attributes: Any) -> None:
        return None


class _NoOpTurn:
    @contextmanager
    def span(self, name: str, **attributes: Any) -> Iterator[Span]:
        yield _NoOpSpan()


class NoOpTracer:
    """Zero-overhead tracer used whenever Langfuse isn't configured."""

    @contextmanager
    def turn(self, *, tenant_id: UUID, conversation_id: UUID, **attributes: Any) -> Iterator[Turn]:
        yield _NoOpTurn()


NOOP_TURN: Turn = _NoOpTurn()
"""Stateless singleton - safe as a frozen-dataclass default (GraphContext.turn)
since it carries no per-request state; every span() call still no-ops."""


def _langfuse_configured(settings: Settings) -> bool:
    return bool(settings.langfuse_public_key and settings.langfuse_secret_key)


def get_tracer(settings: Settings) -> Tracer:
    """Return the active tracer. Today this is always the no-op tracer; when
    the founder adds Langfuse keys and the ``langfuse`` SDK, this is where the
    live backend is selected (the call sites above never change). Kept as a
    single factory so that swap is one function, not a scatter of conditionals.
    """
    if _langfuse_configured(settings):
        # Deliberately not importing langfuse here: the SDK is not a dependency
        # of the free-first stack. Wiring it is a founder step (add the dep,
        # implement a LangfuseTracer with the same Protocol, return it here).
        # Until then, configured-but-unwired falls back to no-op rather than
        # crashing a turn.
        return NoOpTracer()
    return NoOpTracer()
