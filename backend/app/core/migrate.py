"""Plain forward-only migration runner.

Reads ``backend/migrations/*.sql`` in filename order, applies each unapplied file
inside its own transaction, and records it in ``schema_migrations``. ``${VAR}``
placeholders are substituted from the environment before execution (only
``0002_roles.sql`` needs this today). Idempotence lives in the runner: already
applied files are skipped.

CLI: ``uv run python -m app.core.migrate``
"""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path
from typing import Any

import asyncpg

from app.core.config import get_settings

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
_VAR_RE = re.compile(r"\$\{(\w+)\}")


def _render(sql: str, env: dict[str, str]) -> str:
    def repl(match: re.Match[str]) -> str:
        name = match.group(1)
        try:
            return env[name]
        except KeyError as exc:  # pragma: no cover - config error
            raise RuntimeError(
                f"migration references ${{{name}}} but it is not set in the environment"
            ) from exc

    return _VAR_RE.sub(repl, sql)


async def _ensure_table(conn: asyncpg.Connection[Any]) -> None:
    await conn.execute(
        """
        create table if not exists schema_migrations (
          version    text primary key,
          applied_at timestamptz not null default now()
        )
        """
    )


async def _applied(conn: asyncpg.Connection[Any]) -> set[str]:
    rows = await conn.fetch("select version from schema_migrations")
    return {row["version"] for row in rows}


async def run_migrations(dsn: str | None = None) -> list[str]:
    """Apply pending migrations. Returns the versions applied this run."""
    settings = get_settings()
    env = dict(os.environ)
    env.setdefault("WREN_APP_DB_PASSWORD", settings.wren_app_db_password)

    conn = await asyncpg.connect(dsn or settings.database_url)
    applied_now: list[str] = []
    try:
        await _ensure_table(conn)
        already = await _applied(conn)
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = path.name
            if version in already:
                continue
            sql = _render(path.read_text(), env)
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "insert into schema_migrations (version) values ($1)", version
                )
            applied_now.append(version)
    finally:
        await conn.close()
    return applied_now


def main() -> None:
    applied = asyncio.run(run_migrations())
    print("applied: " + ", ".join(applied) if applied else "no pending migrations")


if __name__ == "__main__":
    main()
