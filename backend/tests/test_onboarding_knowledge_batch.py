"""W-11a: PUT /api/onboarding/knowledge/batch publishes N reviewed documents in
one call. A document's own failure - missing, cross-tenant, or a price
conflict on an offering it supports - is data in the response, never a status
code, and never aborts the rest of the batch.

Fixtures mirror test_knowledge_records.py's draft -> save flow (StructuringFake,
uploads_tmp, drafts/upload) and test_onboarding_api.py's tenant-signup / JWT
pattern.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import httpx
import jwt
import pytest
import pytest_asyncio

from app.ingestion import pipeline
from app.llm.dependency import get_embedder_dependency, get_llm_provider
from app.llm.provider import SchemaT
from app.main import app
from app.shared import db
from app.shared.config import get_settings
from app.shared.storage import get_storage
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
            ],
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
    assert "multiple prices found" in rejected_body["failed"][0]["error"]

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


# ---------------------------------------------------------------------------
# W-11a review fixes: a price-conflicted offering must survive the batch call
# so the owner has something to resubmit with accept_price_changes=True, and
# its supporting document's submitted edits must not be lost.
# ---------------------------------------------------------------------------


async def test_price_conflicted_offering_survives_alongside_a_healthy_publish(
    client: httpx.AsyncClient, uploads_tmp: Path
) -> None:
    """Fix 1: an offering wholly supported by price-conflict-failed documents
    must still come back in offering_candidates - unlike a hard failure (not
    found, or a publish-time processing failure), a price conflict is not a
    reason to withhold the offering, since the owner needs it there to
    resubmit with accept_price_changes=True."""
    headers = await _signup_tenant_admin(client)
    conflicted = await _upload_draft(client, headers, filename="conflicted.txt")
    healthy = await _upload_draft(client, headers, filename="healthy.txt")

    response = await client.put(
        "/api/onboarding/knowledge/batch",
        headers=headers,
        json={
            "documents": [
                {"document_id": conflicted["id"], "sections": conflicted["sections"]},
                {"document_id": healthy["id"], "sections": healthy["sections"]},
            ],
            "offerings": [
                {
                    "name": "Screen replacement",
                    "price_options": [12900, 17900],
                    "supporting_document_ids": [conflicted["id"]],
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["published"] == [healthy["id"]]
    assert len(body["failed"]) == 1
    assert body["failed"][0]["document_id"] == conflicted["id"]
    assert {item["name"] for item in body["offering_candidates"]} == {"Screen replacement"}


async def test_price_conflict_document_sections_are_saved_without_publishing(
    client: httpx.AsyncClient, uploads_tmp: Path
) -> None:
    """Fix 2: a price-conflicted document is skipped before publish_record ever
    runs, but the owner's submitted edits to its sections must still be
    persisted so they are not silently discarded."""
    headers = await _signup_tenant_admin(client)
    draft = await _upload_draft(client, headers)
    edited_sections = [dict(section) for section in draft["sections"]]
    edited_sections[0]["body"] = f"{edited_sections[0]['body']} EDITED BY OWNER."

    response = await client.put(
        "/api/onboarding/knowledge/batch",
        headers=headers,
        json={
            "documents": [{"document_id": draft["id"], "sections": edited_sections}],
            "offerings": [
                {
                    "name": "Screen replacement",
                    "price_options": [12900, 17900],
                    "supporting_document_ids": [draft["id"]],
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["failed"][0]["document_id"] == draft["id"]

    record = await client.get(f"/api/knowledge/records/{draft['id']}", headers=headers)
    assert record.json()["status"] == "draft"
    assert record.json()["sections"] == edited_sections


async def test_price_conflict_message_names_every_price_option(
    client: httpx.AsyncClient, uploads_tmp: Path
) -> None:
    """Fix 8: the failure message must name every conflicting price, not just
    the first and last of a longer list."""
    headers = await _signup_tenant_admin(client)
    draft = await _upload_draft(client, headers)
    price_options = [9900, 12900, 15900, 17900]

    response = await client.put(
        "/api/onboarding/knowledge/batch",
        headers=headers,
        json={
            "documents": [{"document_id": draft["id"], "sections": draft["sections"]}],
            "offerings": [
                {
                    "name": "Screen replacement",
                    "price_options": price_options,
                    "supporting_document_ids": [draft["id"]],
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    message = response.json()["failed"][0]["error"]
    for cents in price_options:
        assert f"{cents} cents" in message


async def test_two_documents_supporting_the_same_conflicted_offering_both_fail(
    client: httpx.AsyncClient, uploads_tmp: Path
) -> None:
    """Fix 1/8: when more than one document in the batch supports the same
    conflicting offering, every one of them lands in failed, not just the
    first the loop encounters."""
    headers = await _signup_tenant_admin(client)
    draft_a = await _upload_draft(client, headers, filename="a.txt")
    draft_b = await _upload_draft(client, headers, filename="b.txt")

    response = await client.put(
        "/api/onboarding/knowledge/batch",
        headers=headers,
        json={
            "documents": [
                {"document_id": draft_a["id"], "sections": draft_a["sections"]},
                {"document_id": draft_b["id"], "sections": draft_b["sections"]},
            ],
            "offerings": [
                {
                    "name": "Screen replacement",
                    "price_options": [12900, 17900],
                    "supporting_document_ids": [draft_a["id"], draft_b["id"]],
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["published"] == []
    failed_ids = {item["document_id"] for item in body["failed"]}
    assert failed_ids == {draft_a["id"], draft_b["id"]}


async def test_duplicate_offering_names_in_batch_request_is_422(
    client: httpx.AsyncClient, uploads_tmp: Path
) -> None:
    """The offering-name-uniqueness check stays request-level: two offerings
    that normalize to the same name make the whole request a 422."""
    headers = await _signup_tenant_admin(client)
    draft = await _upload_draft(client, headers)

    response = await client.put(
        "/api/onboarding/knowledge/batch",
        headers=headers,
        json={
            "documents": [{"document_id": draft["id"], "sections": draft["sections"]}],
            "offerings": [
                {"name": "Screen Replacement"},
                {"name": "screen replacement"},
            ],
        },
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("documents", "message"),
    [
        ([], "at least 1 item"),
        ([{"document_id": str(uuid.uuid4()), "sections": []} for _ in range(6)], "at most 5"),
        (
            [
                {"document_id": str(uuid.UUID("00000000-0000-0000-0000-000000000001"))},
                {"document_id": str(uuid.UUID("00000000-0000-0000-0000-000000000001"))},
            ],
            "document_id values must be unique",
        ),
    ],
    ids=["empty", "six-documents", "duplicate-ids"],
)
async def test_batch_request_rejects_invalid_document_cardinality(
    client: httpx.AsyncClient, documents: list[dict[str, Any]], message: str
) -> None:
    headers = await _signup_tenant_admin(client)
    response = await client.put(
        "/api/onboarding/knowledge/batch", headers=headers, json={"documents": documents}
    )
    assert response.status_code == 422
    assert message in response.text


async def test_batch_only_publishes_reviewable_drafts(
    client: httpx.AsyncClient,
    superuser_conn: Any,
) -> None:
    headers = await _signup_tenant_admin(client)
    records = [
        await _upload_draft(client, headers, filename=f"{status}.txt")
        for status in ["ready", "processing", "failed"]
    ]
    for record, status in zip(records, ["ready", "processing", "failed"], strict=True):
        await superuser_conn.execute(
            "update documents set status = $2, "
            "failure_stage = case when $2 = 'failed' then 'structure' else null end, "
            "failure_retryable = case when $2 = 'failed' then true else null end, "
            "failed_at = case when $2 = 'failed' then now() else null end where id = $1",
            record["id"],
            status,
        )

    submitted = [{"heading": "Edited", "body": "This must not be saved.", "kind": "other"}]
    response = await client.put(
        "/api/onboarding/knowledge/batch",
        headers=headers,
        json={
            "documents": [
                {"document_id": record["id"], "sections": submitted} for record in records
            ],
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["published"] == []
    assert {failure["document_id"] for failure in response.json()["failed"]} == {
        record["id"] for record in records
    }
    for record in records:
        current = await client.get(f"/api/knowledge/records/{record['id']}", headers=headers)
        assert current.json()["status"] in {"ready", "processing", "failed"}
        assert current.json()["sections"] != submitted


async def test_price_conflict_does_not_save_sections_on_non_draft(
    client: httpx.AsyncClient, superuser_conn: Any
) -> None:
    headers = await _signup_tenant_admin(client)
    record = await _upload_draft(client, headers, filename="ready-conflict.txt")
    await superuser_conn.execute(
        "update documents set status = 'ready' where id = $1", record["id"]
    )
    submitted = [{"heading": "Edited", "body": "This must not be saved.", "kind": "other"}]
    response = await client.put(
        "/api/onboarding/knowledge/batch",
        headers=headers,
        json={
            "documents": [{"document_id": record["id"], "sections": submitted}],
            "offerings": [
                {
                    "name": "Conflicted service",
                    "price_options": [100, 200],
                    "supporting_document_ids": [record["id"]],
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["failed"][0]["document_id"] == record["id"]
    assert response.json()["failed"][0]["error"] == "document is not a reviewable draft"
    current = await client.get(f"/api/knowledge/records/{record['id']}", headers=headers)
    assert current.json()["status"] == "ready"
    assert current.json()["sections"] != submitted


async def test_storage_failure_is_a_safe_per_document_failure(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = await _signup_tenant_admin(client)
    failed = await _upload_draft(client, headers, filename="storage-failed.txt")
    healthy = await _upload_draft(client, headers, filename="healthy-after-storage.txt")
    storage = get_storage()
    original_put = storage.put

    async def fail_one(key: str, body: bytes) -> None:
        if str(failed["id"]) in key:
            raise OSError("storage credentials leaked")
        await original_put(key, body)

    monkeypatch.setattr(storage, "put", fail_one)
    edited = [{"heading": "Edited", "body": "Storage failure keeps this edit.", "kind": "other"}]
    response = await client.put(
        "/api/onboarding/knowledge/batch",
        headers=headers,
        json={
            "documents": [
                {"document_id": failed["id"], "sections": edited},
                {"document_id": healthy["id"], "sections": healthy["sections"]},
            ],
            "offerings": [
                {"name": "Storage-backed service", "supporting_document_ids": [failed["id"]]}
            ],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["published"] == [healthy["id"]]
    assert body["failed"] == [
        {
            "document_id": failed["id"],
            "error": "We could not save this document. Please retry.",
        }
    ]
    assert body["offering_candidates"] == []
    record = await client.get(f"/api/knowledge/records/{failed['id']}", headers=headers)
    assert record.json()["status"] == "draft"
    assert record.json()["sections"] == edited


async def test_overlapping_batches_publish_a_draft_only_once(
    client: httpx.AsyncClient,
    superuser_conn: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = await _signup_tenant_admin(client)
    draft = await _upload_draft(client, headers, filename="overlap.txt")
    entered_embedding = asyncio.Event()
    release_embedding = asyncio.Event()
    embed_calls = 0
    original_embed_texts = pipeline.embed_texts  # type: ignore[attr-defined]

    async def delayed_embed(*args: Any, **kwargs: Any) -> list[list[float]]:
        nonlocal embed_calls
        embed_calls += 1
        if embed_calls == 1:
            entered_embedding.set()
            await release_embedding.wait()
        return await original_embed_texts(*args, **kwargs)

    monkeypatch.setattr(pipeline, "embed_texts", delayed_embed)
    payload = {"documents": [{"document_id": draft["id"], "sections": draft["sections"]}]}
    first = asyncio.create_task(
        client.put("/api/onboarding/knowledge/batch", headers=headers, json=payload)
    )
    await entered_embedding.wait()
    second = asyncio.create_task(
        client.put("/api/onboarding/knowledge/batch", headers=headers, json=payload)
    )
    async with asyncio.timeout(5):
        while not await superuser_conn.fetchval(  # noqa: ASYNC110 - bounded lock polling
            "select exists ("
            "select 1 from pg_stat_activity as activity "
            "join pg_locks as lock on lock.pid = activity.pid "
            "where not lock.granted and lock.locktype = 'transactionid' "
            "and activity.query like 'select filename, status from documents%'"
            ")"
        ):
            await asyncio.sleep(0)
    release_embedding.set()
    responses = await asyncio.gather(first, second)

    assert sorted(response.json()["published"] for response in responses) == [[], [draft["id"]]]
    failed = next(response.json()["failed"] for response in responses if response.json()["failed"])
    assert failed == [{"document_id": draft["id"], "error": "document is not a reviewable draft"}]
    assert embed_calls == 1
    record = await client.get(f"/api/knowledge/records/{draft['id']}", headers=headers)
    assert record.json()["status"] == "ready"
