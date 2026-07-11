"""T-007: knowledge upload/list, exercised at the API level.

Same client-fixture pattern as test_auth_api.py. Uses a tmp_path for
uploads_dir (via monkeypatch on Settings) so tests never touch a real
backend/var/ directory and clean up automatically.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import jwt
import pytest
import pytest_asyncio

from app.core import db
from app.core.config import get_settings
from app.main import app
from tests.conftest import _app_dsn_for

pytestmark = pytest.mark.db

TEST_JWT_SECRET = "test-only-supabase-jwt-secret-do-not-use-in-prod"  # noqa: S105


@pytest.fixture(autouse=True)
def _env(tmp_path: Path) -> Iterator[None]:
    import os

    original_secret = os.environ.get("SUPABASE_JWT_SECRET")
    original_uploads = os.environ.get("UPLOADS_DIR")
    os.environ["SUPABASE_JWT_SECRET"] = TEST_JWT_SECRET
    os.environ["UPLOADS_DIR"] = str(tmp_path)
    get_settings.cache_clear()
    yield
    if original_secret is None:
        os.environ.pop("SUPABASE_JWT_SECRET", None)
    else:
        os.environ["SUPABASE_JWT_SECRET"] = original_secret
    if original_uploads is None:
        os.environ.pop("UPLOADS_DIR", None)
    else:
        os.environ["UPLOADS_DIR"] = original_uploads
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def client(migrated_db: str) -> AsyncIterator[httpx.AsyncClient]:
    await db.create_pool(dsn=_app_dsn_for(migrated_db), min_size=1, max_size=4)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        await db.close_pool()


def _make_token(user_id: uuid.UUID) -> str:
    now = int(time.time())
    payload = {"sub": str(user_id), "aud": "authenticated", "iat": now, "exp": now + 3600}
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")


async def _signup_tenant_admin(client: httpx.AsyncClient) -> str:
    user_id = uuid.uuid4()
    token = _make_token(user_id)
    slug = f"knowledge-{uuid.uuid4().hex[:8]}"
    response = await client.post(
        "/api/tenants",
        json={"slug": slug, "name": "Knowledge Test Co"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    return token


async def test_upload_happy_path_creates_pending_document(client: httpx.AsyncClient) -> None:
    token = await _signup_tenant_admin(client)
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.post(
        "/api/knowledge/upload",
        headers=headers,
        files={"file": ("faq.md", b"# FAQ\nWe are open 9-5.", "text/markdown")},
        data={"doc_type": "faq"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "faq.md"
    assert body["doc_type"] == "faq"
    assert body["status"] == "pending"
    assert body["error"] is None


async def test_upload_writes_file_under_tenant_directory(
    client: httpx.AsyncClient, tmp_path: Path
) -> None:
    token = await _signup_tenant_admin(client)
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.post(
        "/api/knowledge/upload",
        headers=headers,
        files={"file": ("prices.csv", b"item,price\nhaircut,30", "text/csv")},
        data={"doc_type": "price_list"},
    )
    assert response.status_code == 201
    document_id = response.json()["id"]

    matches = list(tmp_path.rglob(f"{document_id}.csv"))  # noqa: ASYNC240 - test assertion only
    assert len(matches) == 1
    assert matches[0].read_bytes() == b"item,price\nhaircut,30"


async def test_upload_rejects_unsupported_extension(client: httpx.AsyncClient) -> None:
    token = await _signup_tenant_admin(client)
    response = await client.post(
        "/api/knowledge/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("virus.exe", b"whatever", "application/octet-stream")},
        data={"doc_type": "other"},
    )
    assert response.status_code == 422


async def test_upload_rejects_oversized_file(client: httpx.AsyncClient) -> None:
    token = await _signup_tenant_admin(client)
    oversized = b"x" * (10 * 1024 * 1024 + 1)
    response = await client.post(
        "/api/knowledge/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("big.txt", oversized, "text/plain")},
        data={"doc_type": "other"},
    )
    assert response.status_code == 422


async def test_upload_rejects_bad_doc_type(client: httpx.AsyncClient) -> None:
    token = await _signup_tenant_admin(client)
    response = await client.post(
        "/api/knowledge/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("notes.txt", b"hello", "text/plain")},
        data={"doc_type": "not-a-real-type"},
    )
    assert response.status_code == 422


async def test_upload_requires_auth(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/knowledge/upload",
        files={"file": ("notes.txt", b"hello", "text/plain")},
        data={"doc_type": "other"},
    )
    assert response.status_code == 401


async def test_list_is_scoped_per_tenant(client: httpx.AsyncClient) -> None:
    token_a = await _signup_tenant_admin(client)
    token_b = await _signup_tenant_admin(client)

    await client.post(
        "/api/knowledge/upload",
        headers={"Authorization": f"Bearer {token_a}"},
        files={"file": ("a.txt", b"tenant a doc", "text/plain")},
        data={"doc_type": "other"},
    )

    list_a = await client.get("/api/knowledge", headers={"Authorization": f"Bearer {token_a}"})
    list_b = await client.get("/api/knowledge", headers={"Authorization": f"Bearer {token_b}"})
    assert len(list_a.json()) == 1
    assert list_a.json()[0]["filename"] == "a.txt"
    assert list_b.json() == []


async def test_list_empty_for_fresh_tenant(client: httpx.AsyncClient) -> None:
    token = await _signup_tenant_admin(client)
    response = await client.get("/api/knowledge", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json() == []
