"""T-007/T-008: knowledge upload/list/reprocess, exercised at the API level.

Same client-fixture pattern as test_auth_api.py. Uses a tmp_path for
uploads_dir (via monkeypatch on Settings) so tests never touch a real
backend/var/ directory and clean up automatically. The embedder dependency
is overridden with a fake (T-008 wired process_document into the upload
endpoint, so every upload now embeds its chunks).
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any, cast

import asyncpg
import httpx
import jwt
import pytest
import pytest_asyncio

from app.features.knowledge import service
from app.features.knowledge.api import MAX_UPLOAD_BYTES
from app.llm.dependency import get_embedder_dependency, get_llm_provider
from app.llm.embedder import Embedder
from app.llm.provider import LLMProvider
from app.main import app
from app.shared import db
from app.shared.config import get_settings
from tests.conftest import _app_dsn_for
from tests.fakes import EMBEDDING_DIM, ZeroEmbedder

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
    app.dependency_overrides[get_embedder_dependency] = ZeroEmbedder
    # The fixture owns a default provider, the shape test_knowledge_records.py's
    # client fixture already uses. Every draft route resolves get_llm_provider
    # before its body runs, so a test that only asserts a rejection or patches
    # the service layer still needs one injected - otherwise the real factory
    # builds a live SDK client from env and, in an environment with no LLM
    # credentials (CI has none), the route under test answers 500 instead of
    # what it was written to assert. Tests needing particular model behaviour
    # still override this with their own fake.
    app.dependency_overrides[get_llm_provider] = lambda: _MenuProvider()
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(get_embedder_dependency, None)
        app.dependency_overrides.pop(get_llm_provider, None)
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


async def test_upload_happy_path_is_chunked_and_ready(client: httpx.AsyncClient) -> None:
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
    assert body["status"] == "ready"
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


async def test_upload_produces_embedded_chunks(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    token = await _signup_tenant_admin(client)
    response = await client.post(
        "/api/knowledge/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("faq.md", b"We are open weekdays 9-5.", "text/markdown")},
        data={"doc_type": "faq"},
    )
    assert response.status_code == 201
    document_id = response.json()["id"]

    chunk = await superuser_conn.fetchrow(
        "select content, embedding from knowledge_chunks where document_id = $1", document_id
    )
    assert chunk is not None
    assert "open weekdays" in chunk["content"]
    assert chunk["embedding"].dimensions() == EMBEDDING_DIM


async def test_upload_with_unparseable_json_marks_failed(client: httpx.AsyncClient) -> None:
    token = await _signup_tenant_admin(client)
    response = await client.post(
        "/api/knowledge/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("broken.json", b"{not valid json", "application/json")},
        data={"doc_type": "other"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "failed"
    assert body["error"]


async def test_reprocess_replaces_chunks(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    token = await _signup_tenant_admin(client)
    headers = {"Authorization": f"Bearer {token}"}
    upload = await client.post(
        "/api/knowledge/upload",
        headers=headers,
        files={"file": ("faq.md", b"We are open weekdays 9-5.", "text/markdown")},
        data={"doc_type": "faq"},
    )
    document_id = upload.json()["id"]

    reprocess = await client.post(f"/api/knowledge/{document_id}/reprocess", headers=headers)
    assert reprocess.status_code == 200
    assert reprocess.json()["status"] == "ready"

    count = await superuser_conn.fetchval(
        "select count(*) from knowledge_chunks where document_id = $1", document_id
    )
    assert count == 1


async def test_reprocess_unknown_document_is_404(client: httpx.AsyncClient) -> None:
    token = await _signup_tenant_admin(client)
    response = await client.post(
        f"/api/knowledge/{uuid.uuid4()}/reprocess",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


async def test_reprocess_returns_200_even_when_the_result_is_failed(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """W-11a review fix 4: /reprocess was not part of this ticket's brief (only
    retry-draft was asked for), and nothing calls it today - it must keep
    returning the row whatever its status, exactly as before W-11."""
    from app.ingestion import pipeline

    token = await _signup_tenant_admin(client)
    headers = {"Authorization": f"Bearer {token}"}
    upload = await client.post(
        "/api/knowledge/upload",
        headers=headers,
        files={"file": ("faq.md", b"We are open weekdays 9-5.", "text/markdown")},
        data={"doc_type": "faq"},
    )
    document_id = upload.json()["id"]

    async def fail_embed(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("embed-secret")

    monkeypatch.setattr(pipeline, "embed_texts", fail_embed)
    response = await client.post(f"/api/knowledge/{document_id}/reprocess", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["error"]


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
    # Derived from the constant, never a repeated literal: B-4 lowered the cap to
    # sit under Vercel's 4.5MB request-body limit, and a hardcoded size here
    # would have kept passing while testing nothing.
    oversized = b"x" * (MAX_UPLOAD_BYTES + 1)
    response = await client.post(
        "/api/knowledge/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("big.txt", oversized, "text/plain")},
        data={"doc_type": "other"},
    )
    assert response.status_code == 422
    # The owner must get our message, not the platform's opaque 413.
    assert "upload limit" in response.json()["detail"]


async def test_upload_cap_stays_under_the_vercel_body_limit() -> None:
    """The deploy target rejects request bodies over 4.5MB at the edge, before
    the app sees them. If this cap ever rises above that, the 422 above becomes
    unreachable and owners get an unexplained failure instead."""
    assert MAX_UPLOAD_BYTES <= 4 * 1024 * 1024


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


# ---------------------------------------------------------------------------
# W-6: offering extraction runs at ingest, is stored, and is read back
# ---------------------------------------------------------------------------


class _MenuProvider:
    """Stands in for the model on both ingest passes.

    ``StructuredKnowledge`` and ``ExtractedOfferings`` are told apart by a field
    only the first has. The extraction half returns what the real one is
    constrained to return - verbatim spans and a block id, never a number - so
    this test exercises the whole ingest path with the model's contribution
    shaped exactly as it is in production.
    """

    def __init__(self) -> None:
        self.calls = 0

    async def extract(self, *, system_prompt: str, user_input: str, schema: Any) -> Any:
        self.calls += 1
        if "about" in schema.model_fields:
            return schema.model_validate({"offerings": ["Hot Chips"], "prices": ["Hot Chips $10"]})
        block = next(
            (line.split("]")[0].lstrip("[") for line in user_input.splitlines() if "$10." in line),
            "",
        )
        return schema.model_validate(
            {"offerings": [{"name_quote": "Hot Chips", "price_block": block}]}
        )

    async def chat(self, messages: Any) -> str:  # pragma: no cover - unused
        return ""

    async def chat_stream(self, messages: Any) -> Any:  # pragma: no cover - unused
        yield ""


async def test_upload_stores_offering_candidates_and_reads_them_back(
    client: httpx.AsyncClient,
) -> None:
    """W-6: candidates are extracted once at ingest, stored, and read back.

    The predecessor recomputed them inside every read by splitting section lines
    at their first monetary figure. Extraction now costs a model call, so this
    pins both halves: the candidate survives the round trip through the new
    column and the API, and listing documents does not re-run the model.
    """
    from app.llm.dependency import get_llm_provider

    provider = _MenuProvider()
    app.dependency_overrides[get_llm_provider] = lambda: provider
    try:
        token = await _signup_tenant_admin(client)
        headers = {"Authorization": f"Bearer {token}"}
        response = await client.post(
            "/api/knowledge/drafts/upload",
            headers=headers,
            files={"file": ("menu.md", b"Hot Chips are $10.\n", "text/markdown")},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "draft"
        assert body["extraction_status"] == "full"
        candidate = body["offering_candidates"][0]
        assert candidate["name"] == "Hot Chips"
        assert candidate["candidate_id"].startswith("off_")
        assert candidate["source_references"] == [
            {
                "block": "b0",
                "excerpt": "Hot Chips are $10.",
                "supported_fields": ["name", "price"],
            }
        ]

        after_ingest = provider.calls
        listed = await client.get("/api/knowledge/records", headers=headers)
        assert listed.status_code == 200
        # Listing must not re-run extraction - that was the old behaviour, and
        # it now costs a model call per document per read.
        assert provider.calls == after_ingest
        record = next(item for item in listed.json() if item["id"] == body["id"])
        assert record["offering_candidates"] == body["offering_candidates"]
        assert record["extraction_status"] == "full"
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)


# ---------------------------------------------------------------------------
# W-11: an accepted-then-failed draft is stored, not discarded, and retryable
# ---------------------------------------------------------------------------


async def test_draft_upload_processing_failure_persists_as_failed(
    client: httpx.AsyncClient,
) -> None:
    """An upload that passes validation but cannot be turned into text - here,
    bytes that are not valid utf-8 - used to vanish into a 422. W-11 stores it
    as a failed draft instead, so retry-draft has a row to retry."""
    token = await _signup_tenant_admin(client)
    response = await client.post(
        "/api/knowledge/drafts/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("bad.txt", b"\xff\xfe\x00\x01", "text/plain")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "failed"
    assert body["error"]
    assert body["failure_stage"] == "structure"
    assert body["failure_retryable"] is True


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("virus.exe", b"whatever"),
        ("big.txt", b"x" * (MAX_UPLOAD_BYTES + 1)),
        ("empty.txt", b""),
    ],
    # Explicit, because pytest derives an id from the *value*: without these the
    # oversize case's node id is the whole 4MB body, and every line that names
    # the test - a failure header, the short summary, the cache's nodeids file -
    # becomes a 4MB line.
    ids=["unsupported-extension", "oversize", "empty"],
)
async def test_draft_upload_rejects_invalid_files_and_stores_nothing(
    client: httpx.AsyncClient, filename: str, content: bytes
) -> None:
    """The other half of the old rule is unchanged: a rejection at validation
    (bad extension, oversized, empty) still stores nothing at all."""
    token = await _signup_tenant_admin(client)
    headers = {"Authorization": f"Bearer {token}"}
    response = await client.post(
        "/api/knowledge/drafts/upload",
        headers=headers,
        files={"file": (filename, content, "application/octet-stream")},
    )
    assert response.status_code == 422
    records = await client.get("/api/knowledge/records", headers=headers)
    assert records.json() == []


async def test_retry_draft_reprocesses_stored_file_and_publishes_nothing(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    """retry-draft re-reads the file already on disk (never asking for a
    re-upload), lands back at 'draft', and never touches the offerings table -
    publishing stays a separate owner action."""
    from app.llm.dependency import get_llm_provider

    provider = _MenuProvider()
    app.dependency_overrides[get_llm_provider] = lambda: provider
    try:
        token = await _signup_tenant_admin(client)
        headers = {"Authorization": f"Bearer {token}"}
        upload = await client.post(
            "/api/knowledge/drafts/upload",
            headers=headers,
            files={"file": ("menu.md", b"Hot Chips are $10.\n", "text/markdown")},
        )
        assert upload.json()["status"] == "draft"
        document_id = upload.json()["id"]
        tenant_id = await superuser_conn.fetchval(
            "select tenant_id from documents where id = $1", document_id
        )

        # Simulate the failure draft_from_upload would have stored had
        # structuring or extraction raised: the original file is still on
        # disk, untouched, exactly as a real failure would leave it.
        await superuser_conn.execute(
            "update documents set status = 'failed', error = 'synthetic failure', "
            "failure_stage = 'structure', failure_retryable = true, failed_at = now() "
            "where id = $1",
            document_id,
        )

        retry = await client.post(f"/api/knowledge/{document_id}/retry-draft", headers=headers)
        assert retry.status_code == 200
        body = retry.json()
        assert body["status"] == "draft"
        assert body["error"] is None
        assert body["failure_stage"] is None
        assert body["failure_retryable"] is None
        assert body["offering_candidates"][0]["name"] == "Hot Chips"

        offerings_count = await superuser_conn.fetchval(
            "select count(*) from offerings where tenant_id = $1", tenant_id
        )
        assert offerings_count == 0
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)


async def test_retry_draft_unknown_document_is_404(client: httpx.AsyncClient) -> None:
    token = await _signup_tenant_admin(client)
    response = await client.post(
        f"/api/knowledge/{uuid.uuid4()}/retry-draft",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


async def test_retry_draft_on_an_already_good_draft_is_404(client: httpx.AsyncClient) -> None:
    """W-11a review fix 5: retry-draft targets a retryable *failed* document
    only. Calling it on a document already at status='draft' must not silently
    discard its stored structured/offerings for a needless re-run."""
    from app.llm.dependency import get_llm_provider

    app.dependency_overrides[get_llm_provider] = lambda: _MenuProvider()
    try:
        token = await _signup_tenant_admin(client)
        headers = {"Authorization": f"Bearer {token}"}
        upload = await client.post(
            "/api/knowledge/drafts/upload",
            headers=headers,
            files={"file": ("menu.md", b"Hot Chips are $10.\n", "text/markdown")},
        )
        assert upload.json()["status"] == "draft"
        document_id = upload.json()["id"]

        response = await client.post(f"/api/knowledge/{document_id}/retry-draft", headers=headers)
        assert response.status_code == 404
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)


async def test_retry_draft_scoped_to_tenant(client: httpx.AsyncClient) -> None:
    """A document belonging to another tenant must not be reachable."""
    from app.llm.dependency import get_llm_provider

    provider = _MenuProvider()
    app.dependency_overrides[get_llm_provider] = lambda: provider
    try:
        token_a = await _signup_tenant_admin(client)
        token_b = await _signup_tenant_admin(client)
        upload = await client.post(
            "/api/knowledge/drafts/upload",
            headers={"Authorization": f"Bearer {token_a}"},
            files={"file": ("menu.md", b"Hot Chips are $10.\n", "text/markdown")},
        )
        document_id = upload.json()["id"]

        response = await client.post(
            f"/api/knowledge/{document_id}/retry-draft",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert response.status_code == 404
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)


async def test_structure_failure_redacts_exception_and_sets_failed_at(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fail(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("structure-secret")

    monkeypatch.setattr(service, "structure_document", fail)
    token = await _signup_tenant_admin(client)
    response = await client.post(
        "/api/knowledge/drafts/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    body = response.json()
    assert response.status_code == 201
    assert body["status"] == "failed"
    assert body["error"] == "We could not prepare this document for review. Please retry."
    assert "structure-secret" not in body["error"]
    assert body["failed_at"] is not None


async def test_complete_extraction_failure_lands_as_draft_not_failed(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """W-11a review fix 3: extract_offerings's own docstring says status="failed"
    means a degraded-but-reviewable result (fewer candidates, readable sections
    still there), not a hard document failure. Only a raised exception should
    ever land status='failed'."""

    async def extraction(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"status": "failed", "candidates": []}

    async def structure(*args: Any, **kwargs: Any) -> list[dict[str, str]]:
        return [{"heading": "Other information", "body": "hello", "kind": "other"}]

    monkeypatch.setattr(service, "structure_document", structure)
    monkeypatch.setattr(service, "_extraction", extraction)
    token = await _signup_tenant_admin(client)
    response = await client.post(
        "/api/knowledge/drafts/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    body = response.json()
    assert body["status"] == "draft"
    assert body["extraction_status"] == "failed"
    assert body["failure_stage"] is None
    assert body["error"] is None
    assert body["offering_candidates"] == []
    assert body["sections"] == [{"heading": "Other information", "body": "hello", "kind": "other"}]


async def test_partial_extraction_remains_draft(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def extraction(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"status": "partial", "candidates": []}

    async def structure(*args: Any, **kwargs: Any) -> list[dict[str, str]]:
        return [{"heading": "Other information", "body": "hello", "kind": "other"}]

    monkeypatch.setattr(service, "structure_document", structure)
    monkeypatch.setattr(service, "_extraction", extraction)
    token = await _signup_tenant_admin(client)
    response = await client.post(
        "/api/knowledge/drafts/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert response.json()["status"] == "draft"
    assert response.json()["failure_stage"] is None


class _AlwaysFailingExtractProvider:
    """Every ``extract()`` call raises. Both structure_document and
    extract_offerings catch per-segment model failures internally and degrade
    rather than propagate (see their own docstrings) - the model failing is
    never an exception that reaches draft_from_upload, so this proves a
    document can legitimately land at extraction_status='failed' through the
    real pipeline, not just by monkeypatching the service layer."""

    async def extract(self, *, system_prompt: str, user_input: str, schema: Any) -> Any:
        raise RuntimeError("model unavailable")

    async def chat(self, messages: Any) -> str:  # pragma: no cover - unused
        return ""

    async def chat_stream(self, messages: Any) -> Any:  # pragma: no cover - unused
        yield ""


async def test_extraction_failure_via_real_provider_lands_as_draft(
    client: httpx.AsyncClient,
) -> None:
    """End-to-end version of the fix-3 proof above, through the real upload
    endpoint with a genuinely failing provider rather than a mocked service
    function: the document still lands at status='draft' with its readable
    sections intact and extraction_status='failed'."""
    from app.llm.dependency import get_llm_provider

    app.dependency_overrides[get_llm_provider] = lambda: _AlwaysFailingExtractProvider()
    try:
        token = await _signup_tenant_admin(client)
        response = await client.post(
            "/api/knowledge/drafts/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={
                "file": (
                    "notes.txt",
                    b"We are open weekdays 9-5. Call us on 555-1234.",
                    "text/plain",
                )
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "draft"
        assert body["extraction_status"] == "failed"
        assert body["offering_candidates"] == []
        assert body["sections"]
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)


async def test_draft_timeout_stores_retryable_safe_failure(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service, "_DRAFT_TIMEOUT_SECONDS", 0)
    token = await _signup_tenant_admin(client)
    response = await client.post(
        "/api/knowledge/drafts/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    body = response.json()
    assert body["status"] == "failed"
    assert body["failure_retryable"] is True
    assert body["failure_stage"] == "structure"
    assert body["error"] == "We could not prepare this document for review. Please retry."


async def test_retry_failure_redacts_exception_and_keeps_metadata(
    client: httpx.AsyncClient,
    superuser_conn: asyncpg.Connection[Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.llm.dependency import get_llm_provider

    app.dependency_overrides[get_llm_provider] = lambda: _MenuProvider()
    try:
        token = await _signup_tenant_admin(client)
        headers = {"Authorization": f"Bearer {token}"}
        upload = await client.post(
            "/api/knowledge/drafts/upload",
            headers=headers,
            files={"file": ("notes.txt", b"hello", "text/plain")},
        )
        document_id = upload.json()["id"]

        # W-11a review fix 5: retry-draft targets a retryable failed document
        # only, so this document must be parked as one before retrying it -
        # exactly as a real structuring failure would have left it.
        await superuser_conn.execute(
            "update documents set status = 'failed', error = 'placeholder', "
            "failure_stage = 'structure', failure_retryable = true, failed_at = now() "
            "where id = $1",
            document_id,
        )

        async def fail(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("retry-secret")

        monkeypatch.setattr(service, "structure_document", fail)
        response = await client.post(f"/api/knowledge/{document_id}/retry-draft", headers=headers)
        body = response.json()
        assert body["status"] == "failed"
        assert body["error"] == "We could not prepare this document for review. Please retry."
        assert "retry-secret" not in body["error"]
        assert body["failed_at"] is not None
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)


async def test_url_retry_reads_txt_storage(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any], tmp_path: Path
) -> None:
    from app.llm.dependency import get_llm_provider

    app.dependency_overrides[get_llm_provider] = lambda: _MenuProvider()
    try:
        token = await _signup_tenant_admin(client)
        user_id = jwt.decode(
            token, TEST_JWT_SECRET, algorithms=["HS256"], options={"verify_aud": False}
        )["sub"]
        tenant_id = await superuser_conn.fetchval(
            "select tenant_id from users where id = $1", uuid.UUID(user_id)
        )
        row = await service.draft_from_url_text(
            tenant_id=tenant_id,
            document_id=uuid.uuid4(),
            url="https://example.com/info",
            text="We are open weekdays.",
            title="Info",
            provider=cast("LLMProvider", _MenuProvider()),
        )
        assert row is not None
        path = tmp_path / str(tenant_id) / f"{row['id']}.txt"
        assert path.exists()
        await superuser_conn.execute(
            "update documents set status = 'failed', failure_stage = 'structure', "
            "failure_retryable = true, error = 'old' where id = $1",
            row["id"],
        )
        retried = await client.post(
            f"/api/knowledge/{row['id']}/retry-draft", headers={"Authorization": f"Bearer {token}"}
        )
        assert retried.status_code == 200
        assert retried.json()["status"] == "draft"
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)


async def test_embed_failure_retry_demotes_without_embedding_or_publication(
    client: httpx.AsyncClient,
    superuser_conn: asyncpg.Connection[Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.ingestion import pipeline
    from app.llm.dependency import get_llm_provider

    app.dependency_overrides[get_llm_provider] = lambda: _MenuProvider()
    try:
        token = await _signup_tenant_admin(client)
        headers = {"Authorization": f"Bearer {token}"}
        upload = await client.post(
            "/api/knowledge/drafts/upload",
            headers=headers,
            files={"file": ("notes.txt", b"hello", "text/plain")},
        )
        document_id = upload.json()["id"]
        tenant_id = await superuser_conn.fetchval(
            "select tenant_id from documents where id = $1", document_id
        )
        await superuser_conn.execute(
            "insert into knowledge_chunks (tenant_id, document_id, content, embedding, metadata) "
            "values ($1, $2, 'old', $3, '{}')",
            tenant_id,
            document_id,
            [0.0] * EMBEDDING_DIM,
        )
        await superuser_conn.execute(
            "update documents set status = 'failed', failure_stage = 'embed', "
            "failure_retryable = true, failed_at = now() where id = $1",
            document_id,
        )

        async def fail_embed(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("embed must not run")

        monkeypatch.setattr(pipeline, "embed_texts", fail_embed)
        response = await client.post(f"/api/knowledge/{document_id}/retry-draft", headers=headers)
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "draft"
        assert body["error"] is None
        assert body["failure_stage"] is None
        assert (
            await superuser_conn.fetchval(
                "select count(*) from knowledge_chunks where document_id = $1", document_id
            )
            == 0
        )
        assert (
            await superuser_conn.fetchval(
                "select count(*) from offerings where tenant_id = $1", tenant_id
            )
            == 0
        )
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)


class _FailingEmbedder(Embedder):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("embed-secret")


async def test_legacy_save_returns_error_when_embed_fails(
    client: httpx.AsyncClient,
) -> None:
    from app.llm.dependency import get_llm_provider

    app.dependency_overrides[get_llm_provider] = lambda: _MenuProvider()
    try:
        token = await _signup_tenant_admin(client)
        headers = {"Authorization": f"Bearer {token}"}
        upload = await client.post(
            "/api/knowledge/drafts/upload",
            headers=headers,
            files={"file": ("notes.txt", b"hello", "text/plain")},
        )
        document_id = upload.json()["id"]
        app.dependency_overrides[get_embedder_dependency] = _FailingEmbedder
        response = await client.put(
            f"/api/knowledge/records/{document_id}",
            headers=headers,
            json={"sections": [{"heading": "Other information", "body": "hello", "kind": "other"}]},
        )
        assert response.status_code >= 400
        assert "embed-secret" not in response.text
    finally:
        app.dependency_overrides.pop(get_embedder_dependency, None)
        app.dependency_overrides.pop(get_llm_provider, None)
