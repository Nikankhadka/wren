"""Fail-fast configuration guard, run once at app startup.

The migration runner already refuses the ``change-me`` DB password, and the
auth layer rejects an empty JWT secret on the first request - but nothing
stopped a misconfigured API from *booting* and only 500ing later. This guard
closes that gap: outside local/CI, placeholder or empty secrets abort startup
loudly instead of lying dormant until the first authed request.
"""

from __future__ import annotations

from app.shared.config import Settings

# Environments where placeholder secrets are expected and fine.
_DEV_ENVIRONMENTS = frozenset({"local", "ci", "test"})

# The placeholder the migration runner and Terraform both use; never valid live.
_PLACEHOLDER_DB_PASSWORD = "change-me"


class ConfigError(RuntimeError):
    """The process is configured in a way that cannot work: placeholder secrets
    in a real deployment, or a provider leg whose model cannot do the job."""


def check_startup_config(settings: Settings) -> None:
    """Raise :class:`ConfigError` on configuration that cannot work.

    The secrets half is a no-op in local/CI, where placeholder defaults are
    expected. The provider half is not: a model that cannot do structured
    outputs breaks every route and every inspection call in *any* environment,
    and it breaks quietly - the endpoint returns prose with a 200.
    """
    _check_provider_legs(settings)

    if settings.environment.lower() in _DEV_ENVIRONMENTS:
        return

    # Imported here for the same reason _check_provider_legs does it.
    from app.llm.dependency import primary_leg_configured

    missing: list[str] = []
    if not primary_leg_configured(settings):
        # Not a dev-environment concern: local and CI runs stub the provider,
        # and the factory now says so clearly if one slips through. A real
        # deployment without a primary leg answers no customer at all, so it
        # should die here rather than 500 on every turn.
        missing.append(
            f"the primary LLM leg (LLM_PROVIDER={settings.llm_provider!r}) has no "
            "endpoint/model credentials"
        )
    if not settings.supabase_jwt_secret:
        missing.append("SUPABASE_JWT_SECRET is empty")
    db_password = settings.wren_app_db_password
    if not db_password or db_password == _PLACEHOLDER_DB_PASSWORD:
        missing.append("WREN_APP_DB_PASSWORD is unset or still the 'change-me' placeholder")

    if missing:
        raise ConfigError(
            f"refusing to start in environment={settings.environment!r} with "
            f"insecure configuration: {'; '.join(missing)}"
        )


# Groq serves strict json_schema structured outputs only on its gpt-oss line.
# Point a leg at llama-3.3-70b-versatile and every extract() - routing,
# onboarding, inspection - comes back as prose under a 200, which surfaces as
# mysterious validation errors far from the cause. Documented in .env.example
# and enforced here (P-1 US-2).
_GROQ_HOST = "api.groq.com"
_GROQ_STRUCTURED_OUTPUT_MODELS = ("gpt-oss",)


def _check_provider_legs(settings: Settings) -> None:
    # Imported here, not at module scope: app.llm.dependency pulls the embedder
    # module in, and this guard runs before anything has asked for a model.
    from app.llm.dependency import leg_settings

    for leg in ("primary", "fallback", "failover"):
        _, base_url, _, model = leg_settings(settings, leg)
        if not model or _GROQ_HOST not in base_url:
            continue
        if not any(family in model for family in _GROQ_STRUCTURED_OUTPUT_MODELS):
            raise ConfigError(
                f"the {leg} provider leg points at Groq with model {model!r}, which "
                "does not support strict json_schema structured outputs - Groq serves "
                "those only on its gpt-oss models, and every extract() call would "
                "silently return prose. Use openai/gpt-oss-120b (or gpt-oss-20b)."
            )
