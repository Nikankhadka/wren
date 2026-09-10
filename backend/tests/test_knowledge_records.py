"""O-3 knowledge screen: structure a source, review it, save it, remove it.

Two halves: pure tests for the structuring step (no DB, no network - the money
guard is the point) and db-marked tests for the draft -> save -> delete flow
through the real API. No vertical-specific behaviour anywhere: the headings are
the same for every business.
"""

from __future__ import annotations

import io
import time
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import asyncpg
import httpx
import jwt
import pytest
import pytest_asyncio
from pypdf import PdfWriter

from app.features.knowledge.structuring import (
    AS_WRITTEN,
    StructuredKnowledge,
    figures_preserved,
    render_sections,
    structure_document,
)
from app.llm.dependency import get_embedder_dependency, get_llm_provider
from app.llm.provider import SchemaT
from app.main import app
from app.onboarding.flow import normalize_pending_offerings
from app.shared import db
from app.shared.config import get_settings
from tests.conftest import _app_dsn_for
from tests.fakes import BaseFakeProvider, ZeroEmbedder

TEST_JWT_SECRET = "test-only-supabase-jwt-secret-do-not-use-in-prod"  # noqa: S105

_SOURCE = (
    "Northside Repairs fixes phones and laptops.\n"
    "Screen replacement $89. Battery replacement $49.\n"
    "Open Monday to Friday, 9am to 6pm."
)


class StructuringFake(BaseFakeProvider):
    """Returns a fixed structured result, so the tests assert on this module's
    own behaviour rather than on a model's."""

    def __init__(self, payload: dict[str, str] | None = None, *, fail: bool = False) -> None:
        self.payload = payload
        self.fail = fail

    async def extract(
        self, *, system_prompt: str, user_input: str, schema: type[SchemaT]
    ) -> SchemaT:
        if self.fail:
            raise RuntimeError("provider is down")
        return schema.model_validate(self.payload or {})


class SegmentStructuringFake(StructuringFake):
    def __init__(self, failed_marker: str = "") -> None:
        super().__init__()
        self.failed_marker = failed_marker
        self.inputs: list[str] = []

    async def extract(
        self, *, system_prompt: str, user_input: str, schema: type[SchemaT]
    ) -> SchemaT:
        self.inputs.append(user_input)
        if self.failed_marker and self.failed_marker in user_input:
            raise RuntimeError("segment failed")
        return schema.model_validate({"about": [user_input]})


# --- unit: structuring --------------------------------------------------------


async def test_structure_document_returns_only_the_sections_the_source_filled() -> None:
    provider = StructuringFake(
        {
            "about": "A phone and laptop repair shop.",
            "prices": "Screen replacement $89. Battery replacement $49.",
            "hours": "Monday to Friday, 9am to 6pm.",
        }
    )
    sections = await structure_document(_SOURCE, provider=provider)

    assert [section["heading"] for section in sections] == ["Business overview", "Hours"]
    assert sections[0]["kind"] == "business_overview"


async def test_structure_document_keeps_the_source_when_a_figure_is_invented() -> None:
    """The hard rule: a model may reorganise the owner's material, never author
    a price. $95 is not in the source, so the whole structured version goes."""
    provider = StructuringFake({"prices": "Screen replacement $95. Battery replacement $49."})
    sections = await structure_document(_SOURCE, provider=provider)

    assert [section["heading"] for section in sections] == [AS_WRITTEN]
    assert "$89" in sections[0]["body"]


async def test_structure_document_allows_dropping_a_figure() -> None:
    """Keeping less is not inventing - only figures absent from the source fail."""
    provider = StructuringFake({"prices": "Screen replacement $89."})
    sections = await structure_document(_SOURCE, provider=provider)

    assert [section["heading"] for section in sections] == [AS_WRITTEN]


async def test_structure_document_keeps_the_source_when_the_model_fails() -> None:
    sections = await structure_document(_SOURCE, provider=StructuringFake(fail=True))

    assert [section["heading"] for section in sections] == [AS_WRITTEN]
    assert sections[0]["body"] == _SOURCE


async def test_structure_document_keeps_the_source_when_the_model_returns_nothing() -> None:
    sections = await structure_document(_SOURCE, provider=StructuringFake({}))

    assert [section["heading"] for section in sections] == [AS_WRITTEN]


async def test_structure_document_on_empty_text_returns_no_sections() -> None:
    assert await structure_document("   \n\n ", provider=StructuringFake({})) == []


def test_figures_preserved_counts_repeats() -> None:
    assert figures_preserved("$16 and $16", "$16")
    assert not figures_preserved("$16", "$16 and $16")


def test_render_sections_drops_empty_bodies() -> None:
    rendered = render_sections(
        [{"heading": "About", "body": "A shop."}, {"heading": "Prices", "body": "  "}]
    )
    assert rendered == "About\nA shop."


def test_structured_knowledge_defaults_every_field_to_empty() -> None:
    """A model that answers with one field must not fail validation - an empty
    field means 'the source says nothing about this'."""
    structured = StructuredKnowledge.model_validate({"about": "A shop."})
    assert structured.business_overview == ["A shop."]
    assert structured.hours == []


def test_legacy_candidate_match_names_normalize_to_stable_ids() -> None:
    candidates = normalize_pending_offerings(
        [
            {"name": "coffe", "possible_matches": ["coffee drinks"]},
            {"name": "coffee drinks"},
        ]
    )
    assert candidates[0].possible_matches == [candidates[1].candidate_id]


async def test_long_documents_are_structured_in_bounded_segments() -> None:
    source = "\n".join(f"Line {index}" for index in range(4000))
    provider = SegmentStructuringFake()
    sections = await structure_document(source, provider=provider)
    assert len(provider.inputs) > 1
    assert all(len(item) <= 12_000 for item in provider.inputs)
    assert "Line 3999" in sections[0]["body"]


async def test_failed_segment_is_retained_without_losing_successful_segments() -> None:
    source = "good one\n" + ("bad segment\n" * 2500) + "final one"
    provider = SegmentStructuringFake("bad segment")
    sections = await structure_document(source, provider=provider)
    assert any(section["heading"] == "As written" for section in sections)
    assert "good one" in sections[0]["body"]


# --- db: the draft -> save -> delete flow ------------------------------------


@pytest.fixture
def uploads_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path))
    get_settings.cache_clear()
    return tmp_path


def _make_token(user_id: uuid.UUID) -> str:
    now = int(time.time())
    payload = {"sub": str(user_id), "aud": "authenticated", "iat": now, "exp": now + 3600}
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")


@pytest_asyncio.fixture
async def client(
    migrated_db: str, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setenv("SUPABASE_JWT_SECRET", TEST_JWT_SECRET)
    get_settings.cache_clear()
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
        json={"slug": f"know-{uuid.uuid4().hex[:8]}", "name": "Knowledge Test Co"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {token}"}


async def _upload_draft(client: httpx.AsyncClient, headers: dict[str, str]) -> dict[str, Any]:
    response = await client.post(
        "/api/knowledge/drafts/upload",
        headers=headers,
        files={"file": ("about-us.txt", _SOURCE.encode("utf-8"), "text/plain")},
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


@pytest.mark.db
async def test_draft_is_readable_but_answers_nothing(
    client: httpx.AsyncClient, uploads_tmp: Path, superuser_conn: asyncpg.Connection[Any]
) -> None:
    headers = await _signup_tenant_admin(client)
    draft = await _upload_draft(client, headers)

    assert draft["status"] == "draft"
    assert [section["heading"] for section in draft["sections"]] == ["Business overview", "Hours"]

    # Nothing is embedded until the owner saves, so retrieval cannot see it.
    chunks = await superuser_conn.fetchval(
        "select count(*) from knowledge_chunks where document_id = $1", uuid.UUID(draft["id"])
    )
    assert chunks == 0


@pytest.mark.db
async def test_saving_the_reviewed_sections_makes_them_answerable(
    client: httpx.AsyncClient, uploads_tmp: Path, superuser_conn: asyncpg.Connection[Any]
) -> None:
    headers = await _signup_tenant_admin(client)
    draft = await _upload_draft(client, headers)

    # The owner corrects a section before saving - the correction is the record.
    sections = [dict(section) for section in draft["sections"]]
    sections[1]["body"] = "Monday to Saturday, 9am to 6pm."
    response = await client.put(
        f"/api/knowledge/records/{draft['id']}", headers=headers, json={"sections": sections}
    )
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["status"] == "ready"
    assert saved["sections"][1]["body"] == "Monday to Saturday, 9am to 6pm."

    contents = await superuser_conn.fetch(
        "select content from knowledge_chunks where document_id = $1", uuid.UUID(draft["id"])
    )
    assert contents, "saving must chunk and embed the reviewed text"
    assert "Monday to Saturday" in " ".join(row["content"] for row in contents)


@pytest.mark.db
async def test_save_round_trips_complete_reviewed_offering_and_preserves_source(
    client: httpx.AsyncClient, uploads_tmp: Path
) -> None:
    headers = await _signup_tenant_admin(client)
    draft = await _upload_draft(client, headers)
    offering = {
        "candidate_id": "off_reviewed_coffee",
        "name": "Coffee",
        "description": "House blend, served with oat milk on request.",
        "price_cents": 500,
        "sources": ["document", "owner"],
        "source_references": [
            {
                "block": "b3",
                "excerpt": "Coffee is $5 and oat milk is available.",
                "supported_fields": ["name", "description", "price"],
            }
        ],
        "possible_matches": [],
        "price_note": "",
        "needs_review": False,
        "price_options": [],
        "supporting_document_ids": [],
        "support_state": "supported",
    }
    saved = await client.put(
        f"/api/knowledge/records/{draft['id']}",
        headers=headers,
        json={"sections": draft["sections"], "offerings": [offering]},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["offering_candidates"] == [offering]

    source = await client.get(f"/api/knowledge/records/{draft['id']}/source", headers=headers)
    assert source.status_code == 200, source.text
    assert source.json() == {"text": _SOURCE, "is_fallback": False}


@pytest.mark.db
async def test_legacy_source_endpoint_marks_saved_review_as_a_fallback(
    client: httpx.AsyncClient,
    uploads_tmp: Path,
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    headers = await _signup_tenant_admin(client)
    uploaded = await client.post(
        "/api/knowledge/upload",
        headers=headers,
        files={"file": ("legacy.txt", _SOURCE.encode("utf-8"), "text/plain")},
        data={"doc_type": "other"},
    )
    assert uploaded.status_code == 201, uploaded.text
    document_id = uploaded.json()["id"]
    tenant_id = await superuser_conn.fetchval(
        "select tenant_id from documents where id = $1", uuid.UUID(document_id)
    )
    (uploads_tmp / str(tenant_id) / f"{document_id}.source.txt").unlink()
    await client.get(f"/api/knowledge/records/{document_id}", headers=headers)

    source = await client.get(f"/api/knowledge/records/{document_id}/source", headers=headers)
    assert source.status_code == 200, source.text
    assert source.json()["is_fallback"] is True
    assert "A phone and laptop repair shop." in source.json()["text"]


@pytest.mark.db
async def test_onboarding_review_publishes_knowledge_without_writing_offerings(
    client: httpx.AsyncClient,
    uploads_tmp: Path,
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    headers = await _signup_tenant_admin(client)
    buffer = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(buffer)
    uploaded = await client.post(
        "/api/knowledge/drafts/upload",
        headers=headers,
        files={"file": ("menu.pdf", buffer.getvalue(), "application/pdf")},
    )
    assert uploaded.status_code == 201, uploaded.text
    draft = uploaded.json()
    document_id = uuid.UUID(draft["id"])
    tenant_id = await superuser_conn.fetchval(
        "select tenant_id from documents where id = $1", document_id
    )
    original = uploads_tmp / str(tenant_id) / f"{document_id}.pdf"
    original_bytes = original.read_bytes()

    response = await client.put(
        f"/api/onboarding/knowledge/{document_id}",
        headers=headers,
        json={
            "sections": [{"heading": "About", "body": "Owner-reviewed facts."}],
            "offerings": [
                {
                    "name": "Coffee",
                    "description": "House blend",
                    "price_cents": 500,
                    "sources": ["owner", "document"],
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["record"]["status"] == "ready"
    assert response.json()["offering_candidates"][0]["name"] == "Coffee"
    assert (
        await superuser_conn.fetchval(
            "select count(*) from offerings where tenant_id = $1", tenant_id
        )
        == 0
    )
    assert original.read_bytes() == original_bytes


@pytest.mark.db
async def test_saving_moves_the_knowledge_version(
    client: httpx.AsyncClient, uploads_tmp: Path, superuser_conn: asyncpg.Connection[Any]
) -> None:
    """P-4 contract: the pre-load cache is keyed on this, so a save the cache
    cannot see would keep serving the old knowledge."""
    headers = await _signup_tenant_admin(client)
    draft = await _upload_draft(client, headers)
    before = await superuser_conn.fetchval(
        "select updated_at from documents where id = $1", uuid.UUID(draft["id"])
    )

    response = await client.put(
        f"/api/knowledge/records/{draft['id']}",
        headers=headers,
        json={"sections": draft["sections"]},
    )
    assert response.status_code == 200
    after = await superuser_conn.fetchval(
        "select updated_at from documents where id = $1", uuid.UUID(draft["id"])
    )
    assert after > before


@pytest.mark.db
async def test_offering_price_change_requires_explicit_confirmation(
    client: httpx.AsyncClient, uploads_tmp: Path
) -> None:
    headers = await _signup_tenant_admin(client)
    created = await client.post(
        "/api/business/offerings",
        headers=headers,
        json={"name": "Screen replacement", "price_dollars": "80.00"},
    )
    assert created.status_code == 201, created.text

    draft = await _upload_draft(client, headers)
    sections = [{"heading": "Business overview", "body": "Phone repairs while you wait."}]
    payload = {
        "sections": sections,
        "offerings": [{"name": "Screen replacement", "price_cents": 8900}],
    }
    response = await client.put(
        f"/api/knowledge/records/{draft['id']}", headers=headers, json=payload
    )
    assert response.status_code == 409
    assert "price changes need confirmation" in response.json()["detail"]

    confirmed = await client.put(
        f"/api/knowledge/records/{draft['id']}",
        headers=headers,
        json={**payload, "accept_price_changes": True},
    )
    assert confirmed.status_code == 200, confirmed.text
    offerings = await client.get("/api/business/offerings", headers=headers)
    assert offerings.json()[0]["price_cents"] == 8900


@pytest.mark.db
async def test_records_list_carries_the_sections(
    client: httpx.AsyncClient, uploads_tmp: Path
) -> None:
    headers = await _signup_tenant_admin(client)
    await _upload_draft(client, headers)

    response = await client.get("/api/knowledge/records", headers=headers)
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["filename"] == "about-us.txt"
    assert [section["heading"] for section in rows[0]["sections"]] == ["Business overview", "Hours"]


@pytest.mark.db
async def test_a_document_ingested_before_this_screen_is_structured_on_first_view(
    client: httpx.AsyncClient, uploads_tmp: Path
) -> None:
    """The onboarding URL turn and the old console upload store no sections.
    Opening one structures it then, so the screen has one shape for everything."""
    headers = await _signup_tenant_admin(client)
    uploaded = await client.post(
        "/api/knowledge/upload",
        headers=headers,
        files={"file": ("legacy.txt", _SOURCE.encode("utf-8"), "text/plain")},
        data={"doc_type": "other"},
    )
    assert uploaded.status_code == 201, uploaded.text
    document_id = uploaded.json()["id"]

    response = await client.get(f"/api/knowledge/records/{document_id}", headers=headers)
    assert response.status_code == 200
    assert [section["heading"] for section in response.json()["sections"]] == [
        "Business overview",
        "Hours",
    ]

    # Structured once: the second read comes back from the stored column.
    again = await client.get(f"/api/knowledge/records/{document_id}", headers=headers)
    assert again.json()["sections"] == response.json()["sections"]


@pytest.mark.db
async def test_adding_the_same_link_twice_re_reads_it_in_place(
    client: httpx.AsyncClient, uploads_tmp: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same address is the same source. Pasting it again means the site
    changed, so it comes back for review rather than appearing twice."""
    headers = await _signup_tenant_admin(client)

    async def fake_fetch(
        url: str,
        *,
        client: httpx.AsyncClient | None = None,
        **kwargs: Any,
    ) -> bytes:
        return b"<html><body><main>We fix phones. Open weekdays.</main></body></html>"

    monkeypatch.setattr("app.features.knowledge.service.fetch_page", fake_fetch)
    first = await client.post(
        "/api/knowledge/drafts/url", headers=headers, json={"url": "https://example.test/"}
    )
    assert first.status_code == 201, first.text
    await client.put(
        f"/api/knowledge/records/{first.json()['id']}",
        headers=headers,
        json={"sections": first.json()["sections"]},
    )

    second = await client.post(
        "/api/knowledge/drafts/url", headers=headers, json={"url": "https://example.test/"}
    )
    assert second.status_code == 201, second.text
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["status"] == "draft"

    records = (await client.get("/api/knowledge/records", headers=headers)).json()
    assert len(records) == 1


@pytest.mark.db
async def test_deleting_a_record_forgets_its_chunks(
    client: httpx.AsyncClient, uploads_tmp: Path, superuser_conn: asyncpg.Connection[Any]
) -> None:
    headers = await _signup_tenant_admin(client)
    draft = await _upload_draft(client, headers)
    await client.put(
        f"/api/knowledge/records/{draft['id']}",
        headers=headers,
        json={"sections": draft["sections"]},
    )

    response = await client.delete(f"/api/knowledge/records/{draft['id']}", headers=headers)
    assert response.status_code == 204
    remaining = await superuser_conn.fetchval(
        "select count(*) from knowledge_chunks where document_id = $1", uuid.UUID(draft["id"])
    )
    assert remaining == 0
    assert (
        await client.get(f"/api/knowledge/records/{draft['id']}", headers=headers)
    ).status_code == 404


@pytest.mark.db
async def test_another_tenants_record_is_not_reachable(
    client: httpx.AsyncClient, uploads_tmp: Path
) -> None:
    first = await _signup_tenant_admin(client)
    draft = await _upload_draft(client, first)
    second = await _signup_tenant_admin(client)

    assert (
        await client.get(f"/api/knowledge/records/{draft['id']}", headers=second)
    ).status_code == 404
    assert (
        await client.delete(f"/api/knowledge/records/{draft['id']}", headers=second)
    ).status_code == 404
    assert (await client.get("/api/knowledge/records", headers=second)).json() == []
