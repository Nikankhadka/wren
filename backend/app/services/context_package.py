"""P-3: the agent-ready context package.

A turn used to cost three serial LLM calls plus a retrieval round trip before
the customer saw a word. The package removes both from the common case: the
material an answer needs - the owner's profile, the business's name and chosen
voice, and the corpus itself when it fits the budget (O-4) - is assembled once
when the chat opens, cached, and handed to a single tool-calling model call per
turn.

W-9: what the assistant is *told about itself* is no longer part of that
material. The contract is code (``app/agents/contract.py``); the package carries
only the two tenant values that render into it, so the free-text
``tenant_config.system_prompt``/``tone`` pair is read by nothing here any more.

Deterministic: no model calls here, and nothing in this module imports ``llm``.
Assembly is four queries (config, version, offerings, corpus), so a cache miss on the
first message costs a few milliseconds, not a round trip to a provider.

**Why the corpus is stored raw rather than as a finished prompt string.** The
spotlight fence (T-027) uses per-request random delimiters; baking them into a
cached string would freeze one delimiter for the package's whole lifetime and
weaken the fence to a known token. So the package caches what is expensive (the
reads) and each turn builds its own prompt with a fresh spotlight, which is
string work.

ponytail: the cache is a module-level dict, so each container worker keeps its own
copy and reassembles independently - at Stage 1 scale that is a few
milliseconds per worker per knowledge change, not a problem worth a shared
cache. The upgrade path is a shared store keyed identically
(``(tenant_id, knowledge_version)``); nothing else about this module changes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from app.retrieval.types import RetrievedChunk
from app.services.knowledge_version import knowledge_version
from app.services.retrieval import corpus_chars, fits_fast_path, whole_corpus
from app.shared import db
from app.shared.voice import CustomerVoice, voice_from_config

if TYPE_CHECKING:
    from app.shared.db import AppConnection

logger = logging.getLogger("app.services.context_package")

# How long an assembled package may be served before it is rebuilt even though
# its version still matches. The version check already catches every knowledge
# and profile change, so this only bounds how long a process holds material for
# a tenant nobody is talking to any more.
CACHE_TTL_S = 900.0

# The profile keys O-1 captures, in the order a customer-facing answer wants
# them. Keys absent from a tenant's profile are simply skipped - a provisional
# tenant that has not finished onboarding still gets a valid package.
_PROFILE_LABELS: tuple[tuple[str, str], ...] = (
    ("business_name", "Business"),
    ("business_type", "What the business does"),
    ("hours", "Opening hours"),
    ("services", "Services offered"),
    ("headcount", "Team"),
    ("contact", "Contact"),
)

# What the code-owned prompt text costs the corpus budget: the contract plus its
# voice block, at their longest (a 300-character custom voice). The contract text
# lives in ``app/agents/contract.py``, which this module may not import (the
# import contracts in backend/pyproject.toml forbid app.services -> app.agents),
# so the size is pinned here and held to it by a test in test_agent_contract.py.
_CONTRACT_OVERHEAD_CHARS = 3800


@dataclass(frozen=True)
class ActiveOffering:
    """An active catalog row exposed as authoritative customer context."""

    name: str
    description: str
    price_cents: int | None


@dataclass(frozen=True)
class ContextPackage:
    """Everything a turn needs about a tenant, assembled once per version."""

    tenant_id: UUID
    version: datetime
    # W-9: the two tenant values the code-owned contract renders. The business's
    # public name (never the owner's own - see US-2), and the voice, which
    # changes expression and nothing else.
    business_name: str = ""
    voice: CustomerVoice = CustomerVoice()
    profile: dict[str, Any] = field(default_factory=dict)
    offerings: list[ActiveOffering] = field(default_factory=list)
    # Populated only on the fast path; the hybrid path retrieves per turn
    # (there is no query at chat-open time to retrieve against). Catalog
    # projections are deliberately absent from both paths; ``offerings`` above
    # is the authoritative source for what is currently offered.
    chunks: list[RetrievedChunk] = field(default_factory=list)
    fast_path: bool = False
    assembled_at: float = 0.0

    def profile_text(self) -> str:
        """The owner's profile as plain labelled lines, or '' if empty.

        These are the answers to the questions customers actually ask (hours,
        services, how to reach a human), so they belong in the prompt whether or
        not the tenant has uploaded any documents yet.
        """
        return _profile_text(self.profile)

    def offerings_text(self) -> str:
        """The current catalog as deterministic prompt material, or ``''``."""
        return format_offerings(self.offerings)

    def owner_material(self) -> str:
        """All non-chunk tenant material that the answering model received."""
        return "\n\n".join(text for text in (self.profile_text(), self.offerings_text()) if text)

    def is_expired(self, now: float | None = None) -> bool:
        return (now or time.monotonic()) - self.assembled_at > CACHE_TTL_S


async def build_package(conn: AppConnection, tenant_id: UUID) -> ContextPackage:
    """Assemble a package for the tenant's current knowledge version."""
    started = time.perf_counter()
    config_row = await conn.fetchrow(
        "select config from tenant_config where tenant_id = $1", tenant_id
    )
    version = await knowledge_version(conn, tenant_id)

    config = _config_of(config_row["config"] if config_row else None)
    raw_profile = config.get("profile")
    profile: dict[str, Any] = dict(raw_profile) if isinstance(raw_profile, dict) else {}
    business_name = str(profile.get("business_name") or "").strip()
    voice = voice_from_config(config)
    offering_rows = await conn.fetch(
        "select name, description, price_cents from offerings "
        "where tenant_id = $1 and active "
        "order by position, created_at, id",
        tenant_id,
    )
    offerings = [
        ActiveOffering(
            name=row["name"],
            description=row["description"],
            price_cents=row["price_cents"],
        )
        for row in offering_rows
    ]

    # The prompt material the corpus shares its budget with is known only now,
    # so the fast-path decision is made with the real overhead rather than a
    # guess (O-4's overhead_chars).
    overhead = (
        _CONTRACT_OVERHEAD_CHARS + len(_profile_text(profile)) + len(format_offerings(offerings))
    )
    total_chars = await corpus_chars(conn, tenant_id)
    fast_path = fits_fast_path(corpus_chars=total_chars, overhead_chars=overhead)

    package = ContextPackage(
        tenant_id=tenant_id,
        version=version,
        business_name=business_name,
        voice=voice,
        profile=profile,
        offerings=offerings,
        chunks=await whole_corpus(conn, tenant_id) if fast_path else [],
        fast_path=fast_path,
        assembled_at=time.monotonic(),
    )

    logger.info(
        "context package assembled",
        extra={
            "fast_path": package.fast_path,
            "chunks": len(package.chunks),
            "corpus_chars": total_chars,
            "offerings": len(package.offerings),
            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
        },
    )
    return package


def _profile_text(profile: dict[str, Any]) -> str:
    lines = [
        f"- {label}: {profile[key]}"
        for key, label in _PROFILE_LABELS
        if str(profile.get(key) or "").strip()
    ]
    return "\n".join(lines)


def _config_of(raw: object) -> dict[str, Any]:
    config = json.loads(raw) if isinstance(raw, str) else (raw or {})
    return config if isinstance(config, dict) else {}


def format_offerings(offerings: list[ActiveOffering]) -> str:
    """Format active offerings in stable storefront order for model context."""
    if not offerings:
        return ""

    lines = ["Current confirmed offerings:"]
    for offering in offerings:
        line = offering.name
        if offering.description:
            line += f": {offering.description}"
        if offering.price_cents is not None:
            line += f" (${offering.price_cents // 100}.{offering.price_cents % 100:02d})"
        lines.append(f"- {line}")
    return "\n".join(lines)


# --- the cache ----------------------------------------------------------------

_cache: dict[UUID, ContextPackage] = {}
_cache_lock = asyncio.Lock()


async def get_package(conn: AppConnection, tenant_id: UUID) -> ContextPackage:
    """The tenant's package, assembled if the cached one is stale or missing.

    The version is read on every lookup rather than trusted for a TTL window:
    an owner who uploads a menu and immediately asks about it must get the new
    material on the very next turn, and one indexed max query is cheap enough to
    pay for that guarantee every time.
    """
    version = await knowledge_version(conn, tenant_id)
    async with _cache_lock:
        cached = _cache.get(tenant_id)
    if cached is not None and cached.version == version and not cached.is_expired():
        return cached

    # Assembled outside the lock: holding it across four queries would serialize
    # every tenant behind one slow build. Two concurrent misses for the same
    # tenant assemble twice and the second store wins - identical content, since
    # assembly is deterministic for a version.
    package = await build_package(conn, tenant_id)
    async with _cache_lock:
        _cache[tenant_id] = package
    return package


async def prime(tenant_id: UUID) -> None:
    """Warm the cache for a tenant whose chat just opened.

    Opens its own connection because the caller (the public tenant lookup) has
    none, and swallows failures: a cold cache costs a few milliseconds on the
    first message, which is never worth failing a page load over.
    """
    try:
        async with db.tenant_context(tenant_id, "customer") as conn:
            await get_package(conn, tenant_id)
    except Exception:
        logger.warning("context package pre-load failed for %s", tenant_id, exc_info=True)


def clear_cache() -> None:
    """Drop every cached package. For tests and for a process-wide reset."""
    _cache.clear()
