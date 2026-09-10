"""FastAPI dependencies for the configured LLMProvider and Embedder.

Shared by every router that needs one (onboarding, knowledge, chat) so tests
override a single callable and stub every call site at once. Both factories
key off settings enums (LLM_PROVIDER, EMBEDDER) - the reranker's pattern
(app/retrieval/rerank.py) - so providers are swapped by env, never by code.

When a fallback model + API key are configured, the returned provider is a
FailoverProvider: every call is served by the primary and retried once against
the fallback when the primary's own retries are exhausted. This is invisible
to callers - they still see a plain LLMProvider. The fallback vendor is
selected by LLM_FALLBACK_PROVIDER ('zai' default, or 'openai_compat').

This module is the one place env meets providers: it reads the llm_* and
llm_fallback_* settings, picks the vendor, and applies the vendor quirks that
fall outside the OpenAI wire format. 'zai' means Z.ai's GLM Flash line: base
URL defaults to Z.ai when empty, extract uses the looser json_object mode, and
every call sends thinking disabled - all resolved here because the provider
class itself is universal.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from app.llm.azure import AzureOpenAIProvider
from app.llm.embedder import Embedder, get_embedder
from app.llm.failover import FailoverProvider
from app.llm.openai_compat import OpenAICompatProvider
from app.llm.provider import LLMProvider
from app.shared.config import Settings, get_settings
from app.shared.startup import ConfigError

logger = logging.getLogger(__name__)

# Z.ai's OpenAI-compatible base path (their GLM Flash models live under
# /api/paas/v4, not the OpenAI-style /v1).
ZAI_BASE_URL = "https://api.z.ai/api/paas/v4/"

# GLM-4.7-Flash has hidden reasoning tokens enabled by default, which tax
# latency on a budget; every call sends thinking disabled. json_object extract
# is the other Z.ai quirk (they document only json_object, not strict
# json_schema) - see OpenAISDKProvider.
_ZAI_EXTRA_BODY: dict[str, object] = {"thinking": {"type": "disabled"}}


def leg_settings(settings: Settings, leg: str) -> tuple[str, str, str, str]:
    """(provider, base_url, api_key, model) for one leg of the chain.

    One place that knows the ``llm_*`` / ``llm_fallback_*`` / ``llm_failover_*``
    naming, so adding a tier is a settings change rather than a new branch in
    every consumer (the startup guard reads legs through this too).
    """
    if leg == "primary":
        return (
            settings.llm_provider,
            settings.llm_base_url,
            settings.llm_api_key,
            settings.llm_model,
        )
    if leg == "fallback":
        return (
            settings.llm_fallback_provider,
            settings.llm_fallback_base_url,
            settings.llm_fallback_api_key,
            settings.llm_fallback_model,
        )
    if leg == "failover":
        return (
            settings.llm_failover_provider,
            settings.llm_failover_base_url,
            settings.llm_failover_api_key,
            settings.llm_failover_model,
        )
    raise ValueError(f"unknown provider leg {leg!r}")


def _openai_compat(settings: Settings, *, leg: str, zai: bool) -> OpenAICompatProvider:
    _, base_url, api_key, model = leg_settings(settings, leg)
    return OpenAICompatProvider(
        base_url=base_url or (ZAI_BASE_URL if zai else ""),
        api_key=api_key,
        model=model,
        max_tokens_draft=settings.llm_max_tokens_draft,
        max_tokens_extract=settings.llm_max_tokens_extract,
        # T-041: 'off' forces the emulated extract()-based path; 'on' and the
        # default 'auto' use native function calling.
        supports_tools=settings.llm_tool_calling != "off",
        extra_body=_ZAI_EXTRA_BODY if zai else None,
        json_object_extract=zai,
    )


def primary_leg_configured(settings: Settings) -> bool:
    """Whether the primary leg has enough configuration to build a client at all.

    Azure needs both halves of its endpoint/key pair: ``AsyncAzureOpenAI``
    validates them in its constructor and raises ``openai.OpenAIError`` there,
    which - because the primary leg is built during FastAPI dependency
    resolution - used to surface as an opaque 500 from whatever route happened
    to ask for a provider, naming neither the setting nor the leg. Every other
    vendor speaks the OpenAI wire format through ``OpenAICompatProvider``, which
    deliberately tolerates a keyless endpoint (a local Ollama) but cannot invent
    a model name.

    The fallback and failover legs have always answered this question for
    themselves (see ``_leg_provider``); the primary is the leg that did not.
    """
    if settings.llm_provider == "azure":
        return bool(settings.azure_openai_endpoint and settings.azure_openai_api_key)
    return bool(settings.llm_model)


def _unconfigured_error(settings: Settings) -> ConfigError:
    needed = (
        "AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY"
        if settings.llm_provider == "azure"
        else "LLM_MODEL (plus LLM_BASE_URL / LLM_API_KEY for a hosted vendor)"
    )
    return ConfigError(
        f"no LLM provider leg is configured: LLM_PROVIDER={settings.llm_provider!r} "
        f"needs {needed}, and no fallback or failover leg is set either. If this "
        "reached a test, that test has not overridden "
        "app.llm.dependency.get_llm_provider - a route that takes a provider "
        "resolves it before its body runs, including routes that never call a model."
    )


def _leg_provider(settings: Settings, leg: str) -> LLMProvider | None:
    """The provider for one leg, or None when that leg is not configured."""
    provider_name, _, api_key, model = leg_settings(settings, leg)
    if leg == "primary":
        if not primary_leg_configured(settings):
            return None
        if provider_name == "azure":
            return AzureOpenAIProvider(settings)
        return _openai_compat(settings, leg=leg, zai=provider_name == "zai")

    if not model:
        return None
    if not api_key:
        logger.warning(
            "LLM_%s_MODEL set but LLM_%s_API_KEY missing; that leg is disabled",
            leg.upper(),
            leg.upper(),
        )
        return None
    return _openai_compat(settings, leg=leg, zai=provider_name == "zai")


def get_llm_provider() -> LLMProvider:
    """The configured provider chain: primary, then each configured leg after it.

    D15's three tiers are a generous free primary, a fast fallback, and an
    independent failover - and they nest, because a chain of two providers is
    exactly what FailoverProvider already is. ``FailoverProvider(primary,
    FailoverProvider(fallback, failover))`` needs no new class and no chain
    type: each leg's failure hands the call to whatever is left.

    Raises :class:`ConfigError` when no leg is configured. That is a fast,
    self-describing failure by design: the alternative is a vendor SDK raising
    its own error from inside dependency resolution, which reads as a mystery
    500 in a route that has nothing to do with configuration.
    """
    settings = get_settings()
    legs = [
        provider
        for provider in (
            _leg_provider(settings, "primary"),
            _leg_provider(settings, "fallback"),
            _leg_provider(settings, "failover"),
        )
        if provider is not None
    ]
    if not legs:
        raise _unconfigured_error(settings)
    chain = legs[-1]
    for leg in reversed(legs[:-1]):
        chain = FailoverProvider(leg, chain, ttft_budget_s=settings.llm_ttft_budget_s)
    return chain


@lru_cache
def get_embedder_dependency() -> Embedder:
    # Cached (unlike the stateless chat providers) so LocalEmbedder's lazily
    # loaded sentence-transformers model is shared process-wide instead of
    # being re-loaded per request.
    return get_embedder(get_settings())
