"""get_llm_provider wiring: LLM_PROVIDER / LLM_FALLBACK_PROVIDER select the
vendor behavior for each failover position, purely by env.

The provider class itself is tested elsewhere (test_llm_zai.py,
test_llm_provider_retry.py); this file pins the factory's routing: one
universal OpenAICompatProvider, with the 'zai' role distinguished only by the
quirks the factory applies (json_object extract mode, thinking disabled, Z.ai
base URL default).
"""

from __future__ import annotations

from typing import Any

import pytest

from app.llm import dependency
from app.llm.failover import FailoverProvider
from app.llm.openai_compat import OpenAICompatProvider
from app.llm.provider import LLMProvider
from app.shared.config import Settings
from app.shared.startup import ConfigError, check_startup_config

_THINKING_OFF = {"thinking": {"type": "disabled"}}


def _wired(monkeypatch: pytest.MonkeyPatch, **settings_kwargs: Any) -> LLMProvider:
    # The wiring tests must not read backend/.env (real keys, real models) -
    # each call passes every LLM_* field explicitly, including empty values
    # where the test intends "unset" (init kwargs beat dotenv values).
    monkeypatch.setattr(dependency, "get_settings", lambda: Settings(**settings_kwargs))
    return dependency.get_llm_provider()


def test_zai_primary_with_openai_compat_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _wired(
        monkeypatch,
        llm_provider="zai",
        llm_api_key="k",
        llm_model="glm-4.7-flash",
        llm_fallback_provider="openai_compat",
        llm_fallback_base_url="https://openrouter.example.test/v1",
        llm_fallback_api_key="k2",
        llm_fallback_model="google/gemma-4-26b-a4b-it:free",
    )
    assert isinstance(provider, FailoverProvider)
    primary = provider._primary
    assert isinstance(primary, OpenAICompatProvider)
    assert primary._model == "glm-4.7-flash"
    assert primary._json_object_extract is True
    assert primary._extra_body == _THINKING_OFF
    fallback = provider._fallback
    assert isinstance(fallback, OpenAICompatProvider)
    assert fallback._model == "google/gemma-4-26b-a4b-it:free"
    assert fallback._json_object_extract is False
    assert fallback._extra_body == {}
    assert str(fallback._client.base_url).startswith("https://openrouter.example.test")
    assert provider.supports_tools is True


def test_openai_compat_primary_with_default_zai_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pre-existing pairing must keep wiring exactly as before; an empty
    fallback base URL defaults to the Z.ai endpoint."""
    provider = _wired(
        monkeypatch,
        llm_provider="openai_compat",
        llm_base_url="https://openrouter.example.test/v1",
        llm_api_key="k",
        llm_model="google/gemma-4-26b-a4b-it:free",
        llm_fallback_api_key="k2",
        llm_fallback_model="glm-4.7-flash",
        llm_fallback_provider="zai",
        llm_fallback_base_url="",
    )
    assert isinstance(provider, FailoverProvider)
    assert isinstance(provider._primary, OpenAICompatProvider)
    fallback = provider._fallback
    assert isinstance(fallback, OpenAICompatProvider)
    assert fallback._model == "glm-4.7-flash"
    assert fallback._json_object_extract is True
    assert fallback._extra_body == _THINKING_OFF
    assert str(fallback._client.base_url).endswith("api.z.ai/api/paas/v4/")


def test_no_fallback_configuration_returns_the_plain_primary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _wired(
        monkeypatch,
        llm_provider="openai_compat",
        llm_base_url="https://openrouter.example.test/v1",
        llm_api_key="k",
        llm_model="m",
        llm_fallback_api_key="",
        llm_fallback_model="",
        llm_fallback_base_url="",
    )
    assert isinstance(provider, OpenAICompatProvider)
    assert not isinstance(provider, FailoverProvider)


# --- P-1: the three-tier chain ------------------------------------------------

_TIERS: dict[str, Any] = {
    "llm_provider": "openai_compat",
    "llm_base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "llm_api_key": "google-key",
    "llm_model": "gemini-3.5-flash-lite",
    "llm_fallback_provider": "openai_compat",
    "llm_fallback_base_url": "https://api.groq.com/openai/v1",
    "llm_fallback_api_key": "groq-key",
    "llm_fallback_model": "openai/gpt-oss-120b",
    "llm_failover_provider": "openai_compat",
    "llm_failover_base_url": "https://openrouter.example.test/v1",
    "llm_failover_api_key": "openrouter-key",
    "llm_failover_model": "google/gemma-4-26b-a4b-it:free",
}


def _tiers(**overrides: Any) -> dict[str, Any]:
    return {**_TIERS, **overrides}


def test_three_configured_tiers_nest_into_one_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _wired(monkeypatch, **_tiers())

    # primary -> (fallback -> failover): a chain of two providers is what
    # FailoverProvider already is, so three tiers need no new type.
    assert isinstance(provider, FailoverProvider)
    primary = provider._primary
    assert isinstance(primary, OpenAICompatProvider)
    assert primary._model == "gemini-3.5-flash-lite"
    rest = provider._fallback
    assert isinstance(rest, FailoverProvider)
    fallback, failover = rest._primary, rest._fallback
    assert isinstance(fallback, OpenAICompatProvider)
    assert isinstance(failover, OpenAICompatProvider)
    assert fallback._model == "openai/gpt-oss-120b"
    assert failover._model == "google/gemma-4-26b-a4b-it:free"


def test_unconfigured_failover_leg_leaves_a_two_leg_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _wired(monkeypatch, **_tiers(llm_failover_model="", llm_failover_api_key=""))

    assert isinstance(provider, FailoverProvider)
    assert not isinstance(provider._fallback, FailoverProvider)


def test_a_leg_with_a_model_but_no_key_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _wired(monkeypatch, **_tiers(llm_failover_api_key=""))

    assert isinstance(provider, FailoverProvider)
    assert not isinstance(provider._fallback, FailoverProvider)


def test_primary_alone_needs_no_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _wired(
        monkeypatch,
        **_tiers(
            llm_fallback_model="",
            llm_fallback_api_key="",
            llm_failover_model="",
            llm_failover_api_key="",
        ),
    )

    assert not isinstance(provider, FailoverProvider)


def test_an_unconfigured_primary_leg_raises_a_named_config_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bare-environment case: nothing LLM_* set at all, so LLM_PROVIDER keeps
    its 'azure' default with no credentials behind it.

    This used to reach ``AsyncAzureOpenAI``'s constructor, which raises
    ``openai.OpenAIError('Missing credentials...')`` - during FastAPI dependency
    resolution, so it surfaced as a 500 from whichever route happened to want a
    provider, naming neither the leg nor the setting. The fallback and failover
    legs had always guarded themselves; the primary is the one that did not.
    """
    with pytest.raises(ConfigError, match="AZURE_OPENAI_ENDPOINT"):
        _wired(
            monkeypatch,
            llm_provider="azure",
            azure_openai_endpoint="",
            azure_openai_api_key="",
            llm_api_key="",
            llm_model="",
            llm_fallback_api_key="",
            llm_fallback_model="",
            llm_failover_api_key="",
            llm_failover_model="",
        )


def test_an_unconfigured_primary_falls_through_to_the_next_configured_leg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The primary now answers "am I configured?" the same way the other legs
    do, so an unset primary is a skipped leg rather than a crash."""
    provider = _wired(
        monkeypatch,
        **_tiers(
            llm_api_key="",
            llm_model="",
            llm_failover_api_key="",
            llm_failover_model="",
        ),
    )

    assert isinstance(provider, OpenAICompatProvider)
    assert not isinstance(provider, FailoverProvider)
    assert provider._model == "openai/gpt-oss-120b"


def test_groq_leg_on_a_non_gpt_oss_model_refuses_to_start() -> None:
    # Groq serves strict json_schema only on its gpt-oss line; anything else
    # returns prose under a 200, breaking every extract() far from the cause.
    settings = Settings(**_tiers(llm_fallback_model="llama-3.3-70b-versatile"))

    with pytest.raises(ConfigError, match="json_schema"):
        check_startup_config(settings)


def test_groq_leg_on_gpt_oss_is_accepted() -> None:
    check_startup_config(Settings(**_tiers()))
