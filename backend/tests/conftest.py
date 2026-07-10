"""Shared test fixtures.

DB-marked tests run against a dedicated ``wren_test`` database created fresh for
the test session (docker compose db must be up); everything else is unit-level.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import asyncpg
import pytest
import pytest_asyncio

from app.core.config import get_settings
from app.core.migrate import run_migrations

TEST_DB_NAME = "wren_test"


def _admin_dsn() -> str:
    """The superuser DSN from the environment (docker-compose default)."""
    return os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/wren")


def _with_db(dsn: str, dbname: str) -> str:
    parts = urlsplit(dsn)
    return urlunsplit((parts.scheme, parts.netloc, f"/{dbname}", parts.query, parts.fragment))


def _app_dsn_for(base_dsn: str) -> str:
    """The same database as ``base_dsn``, but as the wren_app role.

    Swaps credentials only (host/port/dbname come from ``base_dsn``, i.e. from
    ``migrated_db`` - so this always targets wren_test, never the dev database);
    the password comes from settings, never hardcoded. Shared by test_rls.py and
    test_auth_api.py.
    """
    settings = get_settings()
    parts = urlsplit(base_dsn)
    netloc = f"wren_app:{quote(settings.wren_app_db_password, safe='')}@{parts.hostname}"
    if parts.port:
        netloc = f"{netloc}:{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def _db_available() -> bool:
    import socket

    parts = urlsplit(_admin_dsn())
    try:
        with socket.create_connection((parts.hostname or "localhost", parts.port or 5432), 1):
            return True
    except OSError:
        return False


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if _db_available():
        return
    skip = pytest.mark.skip(reason="postgres not reachable (docker compose up -d db)")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip)


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def migrated_db() -> AsyncIterator[str]:
    """A freshly created, fully migrated test database. Yields its superuser DSN.

    Runs on the session loop; it must only yield plain data (the DSN string),
    never live connections, because tests run on per-function loops.
    """
    admin = await asyncpg.connect(_admin_dsn())
    try:
        await admin.execute(
            f"drop database if exists {TEST_DB_NAME} with (force)"  # noqa: S608 - constant name
        )
        await admin.execute(f"create database {TEST_DB_NAME}")
    finally:
        await admin.close()

    test_dsn = _with_db(_admin_dsn(), TEST_DB_NAME)
    await run_migrations(test_dsn)
    yield test_dsn


@pytest.fixture
async def superuser_conn(migrated_db: str) -> AsyncIterator[asyncpg.Connection[Any]]:
    conn = await asyncpg.connect(migrated_db)
    try:
        yield conn
    finally:
        await conn.close()
