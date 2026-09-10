"""The fail-fast startup guard (app/core/startup.py).

A real deployment must not boot with placeholder/empty secrets and only 500 on
the first authed request - it should refuse to start.
"""

from __future__ import annotations

import pytest

from app.shared.config import Settings
from app.shared.startup import ConfigError, check_startup_config


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "environment": "production",
        "supabase_jwt_secret": "a-real-secret",
        "wren_app_db_password": "a-real-password",
        # Stated rather than inherited: every LLM_* field is left to its default
        # (or, on a developer machine, to backend/.env) otherwise, and a guard
        # that only holds where a real key happens to be present is no guard.
        "llm_provider": "openai_compat",
        "llm_base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "llm_api_key": "a-real-key",
        "llm_model": "gemini-3.5-flash-lite",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_local_environment_tolerates_placeholder_secrets() -> None:
    # The default dev posture: empty/placeholder secrets are expected and fine,
    # and so is having no model behind LLM_PROVIDER - local runs and the test
    # suite stub the provider rather than calling one.
    check_startup_config(
        _settings(
            environment="local",
            supabase_jwt_secret="",
            wren_app_db_password="change-me",
            llm_provider="azure",
            azure_openai_endpoint="",
            azure_openai_api_key="",
            llm_api_key="",
            llm_model="",
        )
    )


def test_ci_environment_is_also_exempt() -> None:
    check_startup_config(_settings(environment="ci", supabase_jwt_secret=""))


def test_production_rejects_empty_jwt_secret() -> None:
    with pytest.raises(ConfigError, match="SUPABASE_JWT_SECRET"):
        check_startup_config(_settings(supabase_jwt_secret=""))


def test_production_rejects_placeholder_db_password() -> None:
    with pytest.raises(ConfigError, match="WREN_APP_DB_PASSWORD"):
        check_startup_config(_settings(wren_app_db_password="change-me"))


def test_production_rejects_an_unconfigured_primary_llm_leg() -> None:
    """A deployment whose primary leg has no credentials answers no customer at
    all. It used to boot anyway and raise openai.OpenAIError on every turn, from
    inside dependency resolution; it now refuses to start, like every other
    secret this guard covers."""
    with pytest.raises(ConfigError, match="primary LLM leg"):
        check_startup_config(
            _settings(
                llm_provider="azure",
                azure_openai_endpoint="",
                azure_openai_api_key="",
                llm_api_key="",
                llm_model="",
            )
        )


def test_production_with_real_secrets_passes() -> None:
    check_startup_config(_settings())
