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

    # Chat LLM provider: 'azure' | 'openai_compat'. 'openai_compat' speaks the
    # OpenAI wire format against any base URL (OpenRouter, Groq, Ollama, ...),
    # so swapping hosted vendors is a config change, never a code change.
    llm_provider: str = "azure"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""

    # Azure OpenAI (used when llm_provider='azure' and/or embedder='azure')
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_chat_deployment: str = "gpt-4o-mini"
    azure_openai_embed_deployment: str = "text-embedding-3-small"

    # Embedder: 'local' | 'azure' - independent of llm_provider on purpose
    # (local embeddings + hosted chat is the default $0 stack). embedding_dim
    # must match knowledge_chunks.embedding's vector(N) (migration 0010);
    # pointing at a model with a different dimension needs a migration + re-ingest.
    embedder: str = "local"
    local_embed_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384

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
