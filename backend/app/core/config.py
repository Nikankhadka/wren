from __future__ import annotations

from functools import lru_cache
from urllib.parse import quote, urlsplit, urlunsplit

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, sourced from the environment / local .env.

    Field names map to upper-case env vars (``database_url`` <- ``DATABASE_URL``).
    Only names appear in ``.env.example``; real values live in local ``.env`` and,
    in production, a secrets manager.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/wren"
    wren_app_db_password: str = "change-me"

    # Supabase auth (wired in T-004)
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_jwt_secret: str = ""

    # LLM provider (wired in T-008)
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_chat_deployment: str = "gpt-4o-mini"
    azure_openai_embed_deployment: str = "text-embedding-3-small"

    # Reranker (T-009): 'cohere' | 'local'
    reranker: str = "local"
    cohere_api_key: str = ""

    # Uploads root (T-007)
    uploads_dir: str = "var/uploads"

    @property
    def app_database_url(self) -> str:
        """The same database, but as the un-privileged ``wren_app`` role the API uses."""
        parts = urlsplit(self.database_url)
        netloc = f"wren_app:{quote(self.wren_app_db_password, safe='')}@{parts.hostname}"
        if parts.port:
            netloc = f"{netloc}:{parts.port}"
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


@lru_cache
def get_settings() -> Settings:
    return Settings()
