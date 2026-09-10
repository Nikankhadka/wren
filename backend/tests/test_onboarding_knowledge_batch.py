"""W-11a: PUT /api/onboarding/knowledge/batch publishes N reviewed documents in
one call. A document's own failure - missing, cross-tenant, or a price
conflict on an offering it supports - is data in the response, never a status
code, and never aborts the rest of the batch.

Fixtures mirror test_knowledge_records.py's draft -> save flow (StructuringFake,
uploads_tmp, drafts/upload) and test_onboarding_api.py's tenant-signup / JWT
pattern.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import httpx
import jwt
import pytest
import pytest_asyncio

from app.llm.dependency import get_embedder_dependency, get_llm_provider
from app.llm.provider import SchemaT
from app.main import app
from app.shared import db
from app.shared.config import get_settings
from tests.conftest import _app_dsn_for
from tests.fakes import BaseFakeProvider, ZeroEmbedder

pytestmark = pytest.mark.db

TEST_JWT_SECRET = "test-only-supabase-jwt-secret-do-not-use-in-prod"  # noqa: S105

_SOURCE = (
    "Northside Repairs fixes phones and laptops.\n"
    "Screen replacement $89. Battery replacement $49.\n"
    "Open Monday to Friday, 9am to 6pm."
)


class StructuringFake(BaseFakeProvider):
    """A fixed structuring/extraction result, so drafts land in 'draft' rather
    than 'failed' without needing a real model call."""

    def __init__(self, payload: dict[str, str] | None = None) -> None:
        self.payload = payload

    async def extract(
        self, *, system_prompt: str, user_input: str, schema: type[SchemaT]
    ) -> SchemaT:
        return schema.model_validate(self.payload or {})


@pytest.fixture
def uploads_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path))
    get_settings.cache_clear()
    return tmp_path


@pytest.fixture(autouse=True)
def _supabase_jwt_secret_env() -> Iterator[None]:
    import os

    original = os.environ.get("SUPABASE_JWT_SECRET")
    os.environ["SUPABASE_JWT_SECRET"] = TEST_JWT_SECRET
    get_settings.cache_clear()
    yield
    if original is None:
        os.environ.pop("SUPABASE_JWT_SECRET", None)
    else:
        os.environ["SUPABASE_JWT_SECRET"] = original
    get_settings.cache_clear()


def _make_token(user_id: uuid.UUID) -> str:
    now = int(time.time())
    payload = {"sub": str(user_id), "aud": "authenticated", "iat": now, "exp": now + 3600}
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")


@pytest_asyncio.fixture
async def client(migrated_db: str) -> AsyncIterator[httpx.AsyncClient]:
    await db.create_pool(dsn=_app_dsn_for(migrated_db), min_size=1, max_size=4)
    app.dependency_overrides[get_embedder_dependency] = ZeroEmbedder
    app.dependency_overrides[get_llm_provider] = lambda: StructuringFake(
        {"about": "A phone and laptop repair shop.", "hours": "Monday to Friday, 9am to 6pm."}
    )
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(get_embedder_dependency, None)
        app.dependency_overrides.pop(get_llm_provider, None)
        await db.close_pool()


async def _signup_tenant_admin(client: httpx.AsyncClient) -> dict[str, str]:
    token = _make_token(uuid.uuid4())
    response = await client.post(
        "/api/tenants",
        json={"slug": f"batch-{uuid.uuid4().hex[:8]}", "name": "Batch Test Co"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {token}"}


async def _upload_draft(
    client: httpx.AsyncClient, headers: dict[str, str], filename: str = "about-us.txt"
) -> dict[str, Any]:
    response = await client.post(
        "/api/knowledge/drafts/upload",
        headers=headers,
        files={"file": (filename, _SOURCE.encode("utf-8"), "text/plain")},
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def test_one_failing_document_does_not_abort_the_rest_of_the_batch(
    client: httpx.AsyncClient, uploads_tmp: Path
) -> None:
    headers = await _signup_tenant_admin(client)
    draft = await _upload_draft(client, headers)
    missing_id = uuid.uuid4()

    response = await client.put(
        "/api/onboarding/knowledge/batch",
        headers=headers,
        json={
            "documents": [
                {"document_id": draft["id"], "sections": draft["sections"]},
                {"document_id": str(missing_id), "sections": []},
            ]
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["published"] == [draft["id"]]
    assert body["failed"] == [{"document_id": str(missing_id), "error": "document not found"}]

    # The failed document was never touched by publish_record - it still does
    # not exist, rather than having been half-created or corrupted.
    still_missing = await client.get(f"/api/knowledge/records/{missing_id}", headers=headers)
    assert still_missing.status_code == 404

    published_record = await client.get(f"/api/knowledge/records/{draft['id']}", headers=headers)
    assert published_record.json()["status"] == "ready"


async def test_offering_wholly_supported_by_a_failed_document_is_withheld(
    client: httpx.AsyncClient, uploads_tmp: Path
) -> None:
    missing_id = uuid.uuid4()
    headers = await _signup_tenant_admin(client)

    response = await client.put(
        "/api/onboarding/knowledge/batch",
        headers=headers,
        json={
            "documents": [{"document_id": str(missing_id), "sections": []}],
            "offerings": [
                {"name": "Document-only special", "supporting_document_ids": [str(missing_id)]},
                {"name": "Owner special", "supporting_document_ids": []},
            ],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert {item["name"] for item in body["offering_candidates"]} == {"Owner special"}

    # The withheld list is what got persisted, not just what this call echoed.
    state = await client.get("/api/onboarding/state", headers=headers)
    assert {item["name"] for item in state.json()["offering_candidates"]} == {"Owner special"}


async def test_cross_tenant_document_fails_without_a_500(
    client: httpx.AsyncClient, uploads_tmp: Path
) -> None:
    other_headers = await _signup_tenant_admin(client)
    other_draft = await _upload_draft(client, other_headers, filename="other-tenant.txt")

    headers = await _signup_tenant_admin(client)
    response = await client.put(
        "/api/onboarding/knowledge/batch",
        headers=headers,
        json={"documents": [{"document_id": other_draft["id"], "sections": []}]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["published"] == []
    assert body["failed"] == [{"document_id": other_draft["id"], "error": "document not found"}]

    # The other tenant's document is unaffected.
    untouched = await client.get(
        f"/api/knowledge/records/{other_draft['id']}", headers=other_headers
    )
    assert untouched.status_code == 200
    assert untouched.json()["status"] == "draft"


async def test_price_conflict_fails_only_that_document_unless_accepted(
    client: httpx.AsyncClient, uploads_tmp: Path
) -> None:
    headers = await _signup_tenant_admin(client)
    draft = await _upload_draft(client, headers)

    payload = {
        "documents": [{"document_id": draft["id"], "sections": draft["sections"]}],
        "offerings": [
            {
                "name": "Screen replacement",
                "price_options": [12900, 17900],
                "supporting_document_ids": [draft["id"]],
            }
        ],
    }

    rejected = await client.put("/api/onboarding/knowledge/batch", headers=headers, json=payload)
    assert rejected.status_code == 200, rejected.text
    rejected_body = rejected.json()
    assert rejected_body["published"] == []
    assert len(rejected_body["failed"]) == 1
    assert rejected_body["failed"][0]["document_id"] == draft["id"]
    assert "price changes need confirmation" in rejected_body["failed"][0]["error"]

    # A price-conflicted document is skipped entirely - never handed to
    # publish_record - so it is still exactly where the upload left it.
    still_draft = await client.get(f"/api/knowledge/records/{draft['id']}", headers=headers)
    assert still_draft.json()["status"] == "draft"

    accepted = await client.put(
        "/api/onboarding/knowledge/batch",
        headers=headers,
        json={**payload, "accept_price_changes": True},
    )
    assert accepted.status_code == 200, accepted.text
    accepted_body = accepted.json()
    assert accepted_body["failed"] == []
    assert accepted_body["published"] == [draft["id"]]
