"""E-6: the Booking page API - one read for the screen, links, and the cover."""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import jwt
import pytest
import pytest_asyncio

from app.features.business import api as business_api
from app.features.business import service as business_service
from app.features.business.media import UploadedMedia
from app.llm.dependency import get_embedder_dependency
from app.main import app
from app.services.knowledge_version import knowledge_version
from app.shared import db
from app.shared.config import get_settings
from tests.conftest import _app_dsn_for
from tests.fakes import ZeroEmbedder

pytestmark = pytest.mark.db

TEST_JWT_SECRET = "test-only-supabase-jwt-secret-do-not-use-in-prod"  # noqa: S105

# A one-pixel PNG - a real image header, so the mime check is exercised against
# something a browser would actually produce.
PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100" + "05" * 8
)


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


@pytest.fixture(autouse=True)
def _disable_external_cloudinary(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep API tests deterministic even when a developer has live keys set."""

    class UnconfiguredCloudinary:
        is_configured = False

    monkeypatch.setattr(business_api, "Cloudinary", lambda: UnconfiguredCloudinary())
    monkeypatch.setattr(business_service, "Cloudinary", lambda: UnconfiguredCloudinary())


@pytest_asyncio.fixture
async def client(migrated_db: str) -> AsyncIterator[httpx.AsyncClient]:
    await db.create_pool(dsn=_app_dsn_for(migrated_db), min_size=1, max_size=4)
    app.dependency_overrides[get_embedder_dependency] = ZeroEmbedder
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(get_embedder_dependency, None)
        await db.close_pool()


def _make_token(user_id: uuid.UUID) -> str:
    now = int(time.time())
    return jwt.encode(
        {"sub": str(user_id), "aud": "authenticated", "iat": now, "exp": now + 3600},
        TEST_JWT_SECRET,
        algorithm="HS256",
    )


async def _signup(client: httpx.AsyncClient) -> tuple[dict[str, str], uuid.UUID]:
    token = _make_token(uuid.uuid4())
    response = await client.post(
        "/api/tenants",
        json={"slug": f"biz-{uuid.uuid4().hex[:8]}", "name": "Business Test Co"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {token}"}, uuid.UUID(response.json()["tenant_id"])


async def test_page_reads_as_the_screen_renders(client: httpx.AsyncClient) -> None:
    headers, _ = await _signup(client)
    response = await client.get("/api/business/page", headers=headers)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    # A business that has said nothing yet still gets a coherent page: its name,
    # and every other part empty rather than absent.
    assert body["name"] == "Business Test Co"
    assert body["tagline"] is None
    assert body["links"] == {}
    assert body["has_cover"] is False
    assert body["slug"].startswith("biz-")


async def test_owner_manages_offerings_and_the_list_reads_the_current_rows(
    client: httpx.AsyncClient,
) -> None:
    headers, tenant_id = await _signup(client)

    created = await client.post(
        "/api/business/offerings",
        json={
            "name": "Screen repair",
            "description": "Most models",
            "price_dollars": "89.50",
            "category": "Screen repairs",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    offering = created.json()
    assert offering["price_cents"] == 8950

    listed = await client.get("/api/business/offerings", headers=headers)
    assert listed.json() == [
        {
            "id": offering["id"],
            "name": "Screen repair",
            "description": "Most models",
            "price_cents": 8950,
            "category": "Screen repairs",
            "media": None,
        }
    ]

    async with db.tenant_context(tenant_id, "customer") as conn:
        before = await knowledge_version(conn, tenant_id)

    changed = await client.patch(
        f"/api/business/offerings/{offering['id']}",
        json={"name": "Screen replacement", "price_dollars": "99"},
        headers=headers,
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["price_cents"] == 9900
    assert (await client.get("/api/business/offerings", headers=headers)).json() == [
        {
            "id": offering["id"],
            "name": "Screen replacement",
            "description": "Most models",
            "price_cents": 9900,
            "category": "Screen repairs",
            "media": None,
        }
    ]

    async with db.tenant_context(tenant_id, "customer") as conn:
        after_update = await knowledge_version(conn, tenant_id)
        assert after_update > before

    deleted = await client.delete(f"/api/business/offerings/{offering['id']}", headers=headers)
    assert deleted.status_code == 204, deleted.text
    assert (await client.get("/api/business/offerings", headers=headers)).json() == []
    async with db.tenant_context(tenant_id, "customer") as conn:
        assert await knowledge_version(conn, tenant_id) > after_update


async def test_youtube_offering_media_does_not_require_cloudinary(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, _ = await _signup(client)
    created = await client.post(
        "/api/business/offerings", json={"name": "Repair video"}, headers=headers
    )
    offering_id = created.json()["id"]

    class UnconfiguredCloudinary:
        is_configured = False

    monkeypatch.setattr(business_service, "Cloudinary", UnconfiguredCloudinary)
    response = await client.put(
        f"/api/business/offerings/{offering_id}/media/url",
        json={"url": "https://youtu.be/example"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "type": "video",
        "provider": "youtube",
        "url": "https://youtu.be/example",
        "poster_url": None,
    }
    assert (
        await client.delete(f"/api/business/offerings/{offering_id}/media", headers=headers)
    ).status_code == 204


async def test_cloudinary_cover_is_reported_and_legacy_cover_is_cleared_on_delete(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, tenant_id = await _signup(client)

    class FakeCloudinary:
        is_configured = True

        async def upload(self, **_: Any) -> UploadedMedia:
            return UploadedMedia(
                type="image",
                provider="cloudinary",
                url="https://res.cloudinary.com/demo/image/upload/cover.jpg",
                public_id="tenants/test/cover",
            )

        async def delete(self, **_: Any) -> None:
            return None

    fake = FakeCloudinary()
    monkeypatch.setattr(business_api, "Cloudinary", lambda: fake)
    monkeypatch.setattr(business_service, "Cloudinary", lambda: fake)

    put = await client.put(
        "/api/business/cover",
        files={"file": ("cover.png", PNG_1PX, "image/png")},
        headers=headers,
    )
    assert put.status_code == 204, put.text
    page = await client.get("/api/business/page", headers=headers)
    assert page.json()["has_cover"] is True
    assert page.json()["cover_url"].endswith("cover.jpg")

    deleted = await client.delete("/api/business/cover", headers=headers)
    assert deleted.status_code == 204, deleted.text
    assert (await client.get("/api/business/page", headers=headers)).json()["has_cover"] is False
    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        assert (
            await conn.fetchval(
                "select count(*) from tenant_media where tenant_id=$1 and role='cover'", tenant_id
            )
            == 0
        )


async def test_offerings_are_tenant_scoped(client: httpx.AsyncClient) -> None:
    headers, _ = await _signup(client)
    other_headers, _ = await _signup(client)
    created = await client.post(
        "/api/business/offerings",
        json={"name": "Private service"},
        headers=headers,
    )
    offering_id = created.json()["id"]

    assert (await client.get("/api/business/offerings", headers=other_headers)).json() == []
    assert (
        await client.patch(
            f"/api/business/offerings/{offering_id}",
            json={"name": "Leaked service"},
            headers=other_headers,
        )
    ).status_code == 404
    deleted = await client.delete(f"/api/business/offerings/{offering_id}", headers=other_headers)
    assert deleted.status_code == 404


@pytest.mark.parametrize("field", ["name", "description"])
async def test_a_null_offering_field_is_refused_not_a_500(
    client: httpx.AsyncClient, field: str
) -> None:
    """Both columns are `not null`. An explicit null used to reach the UPDATE
    and raise a constraint violation the owner saw as a 500; absence, not null,
    is how a field is left unchanged."""
    headers, _ = await _signup(client)
    created = await client.post(
        "/api/business/offerings",
        json={"name": "Screen repair", "description": "Same day"},
        headers=headers,
    )
    offering_id = created.json()["id"]

    response = await client.patch(
        f"/api/business/offerings/{offering_id}", json={field: None}, headers=headers
    )
    assert response.status_code == 422, response.text

    unchanged = (await client.get("/api/business/offerings", headers=headers)).json()[0]
    assert unchanged["name"] == "Screen repair"
    assert unchanged["description"] == "Same day"


@pytest.mark.parametrize("price", ["-1", "1.999", "NaN", "1000001"])
async def test_offering_prices_are_validated(client: httpx.AsyncClient, price: str) -> None:
    headers, _ = await _signup(client)
    response = await client.post(
        "/api/business/offerings",
        json={"name": "Screen repair", "price_dollars": price},
        headers=headers,
    )
    assert response.status_code == 422, response.text


async def test_links_round_trip_and_merge(client: httpx.AsyncClient) -> None:
    headers, _ = await _signup(client)
    saved = await client.patch(
        "/api/business/links",
        json={"links": {"instagram": "https://instagram.com/sababa"}},
        headers=headers,
    )
    assert saved.status_code == 200, saved.text
    assert saved.json() == {"instagram": "https://instagram.com/sababa"}

    # A second write adds a slot without clearing the first.
    saved = await client.patch(
        "/api/business/links",
        json={"links": {"facebook": "https://facebook.com/sababa"}},
        headers=headers,
    )
    assert saved.json() == {
        "instagram": "https://instagram.com/sababa",
        "facebook": "https://facebook.com/sababa",
    }
    page = await client.get("/api/business/page", headers=headers)
    assert page.json()["links"]["facebook"] == "https://facebook.com/sababa"


async def test_an_empty_link_clears_that_slot(client: httpx.AsyncClient) -> None:
    headers, _ = await _signup(client)
    await client.patch(
        "/api/business/links", json={"links": {"google": "https://g.example"}}, headers=headers
    )
    cleared = await client.patch(
        "/api/business/links", json={"links": {"google": ""}}, headers=headers
    )
    assert cleared.json() == {}


@pytest.mark.parametrize(
    "url",
    ["javascript:alert(1)", "data:text/html,<script>", "not a url", "ftp://example.com"],
)
async def test_a_link_must_be_a_real_web_address(client: httpx.AsyncClient, url: str) -> None:
    """These render as links a customer clicks, so the scheme allowlist is the
    guard against one arriving through the owner's own settings."""
    headers, _ = await _signup(client)
    response = await client.patch(
        "/api/business/links", json={"links": {"website": url}}, headers=headers
    )
    assert response.status_code == 422, response.text


async def test_an_unknown_link_slot_is_refused(client: httpx.AsyncClient) -> None:
    headers, _ = await _signup(client)
    response = await client.patch(
        "/api/business/links", json={"links": {"tiktok": "https://tiktok.com/@x"}}, headers=headers
    )
    assert response.status_code == 422


async def test_cover_round_trips(client: httpx.AsyncClient) -> None:
    headers, _ = await _signup(client)
    assert (await client.get("/api/business/cover", headers=headers)).status_code == 404

    put = await client.put(
        "/api/business/cover",
        files={"file": ("cover.png", PNG_1PX, "image/png")},
        headers=headers,
    )
    assert put.status_code == 204, put.text

    got = await client.get("/api/business/cover", headers=headers)
    assert got.status_code == 200
    assert got.content == PNG_1PX
    assert got.headers["content-type"].startswith("image/png")
    assert got.headers["etag"]
    assert "private" in got.headers["cache-control"]

    assert (await client.get("/api/business/page", headers=headers)).json()["has_cover"] is True

    assert (await client.delete("/api/business/cover", headers=headers)).status_code == 204
    assert (await client.get("/api/business/cover", headers=headers)).status_code == 404


async def test_a_second_upload_replaces_the_first(client: httpx.AsyncClient) -> None:
    headers, _ = await _signup(client)
    await client.put(
        "/api/business/cover", files={"file": ("a.png", PNG_1PX, "image/png")}, headers=headers
    )
    await client.put(
        "/api/business/cover",
        files={"file": ("b.jpg", b"\xff\xd8\xff-second", "image/jpeg")},
        headers=headers,
    )
    got = await client.get("/api/business/cover", headers=headers)
    assert got.content == b"\xff\xd8\xff-second"
    assert got.headers["content-type"].startswith("image/jpeg")


async def test_storefront_exposes_only_owner_published_content(client: httpx.AsyncClient) -> None:
    headers, _tenant_id = await _signup(client)
    tenant = await client.get("/api/business/page", headers=headers)
    slug = tenant.json()["slug"]
    offering = await client.post(
        "/api/business/offerings",
        json={
            "name": "Screen repair",
            "description": "Repairs for common phone screens.",
            "price_dollars": "89.50",
        },
        headers=headers,
    )
    assert offering.status_code == 201, offering.text
    await client.patch(
        "/api/business/links",
        json={"links": {"website": "https://example.com"}},
        headers=headers,
    )
    assert (
        await client.put(
            "/api/business/cover",
            files={"file": ("cover.png", PNG_1PX, "image/png")},
            headers=headers,
        )
    ).status_code == 204
    storefront = await client.get(f"/api/public/tenant/{slug}/storefront")
    assert storefront.status_code == 200, storefront.text
    body = storefront.json()
    assert body["name"] == "Business Test Co"
    # The owner's own figure, in the integer cents it was stored as - the page
    # formats it and nothing recomputes it.
    assert body["offerings"] == [
        {
            "id": offering.json()["id"],
            "name": "Screen repair",
            "description": "Repairs for common phone screens.",
            "price_cents": 8950,
            "category": None,
            "media": None,
        }
    ]
    assert "about" not in body
    assert "reviews" not in body
    assert body["links"] == {"website": "https://example.com"}
    assert body["has_cover"] is True

    image = await client.get(f"/api/public/tenant/{slug}/cover")
    assert image.status_code == 200
    assert image.content == PNG_1PX
    # Shared, but revalidated: an owner who replaces their cover must not be
    # showing customers the old one for the rest of the hour.
    cache_control = image.headers["cache-control"]
    assert "public" in cache_control
    assert "must-revalidate" in cache_control
    assert image.headers["etag"]


async def test_a_priceless_offering_reaches_the_storefront_with_no_price(
    client: httpx.AsyncClient,
) -> None:
    """A price is optional. An offering without one shows no price, rather than
    a zero or a figure the page made up to fill the space."""
    headers, _tenant_id = await _signup(client)
    slug = (await client.get("/api/business/page", headers=headers)).json()["slug"]
    created = await client.post(
        "/api/business/offerings", json={"name": "Free diagnosis"}, headers=headers
    )
    assert created.status_code == 201, created.text
    assert created.json()["price_cents"] is None

    body = (await client.get(f"/api/public/tenant/{slug}/storefront")).json()
    assert body["offerings"] == [
        {
            "id": created.json()["id"],
            "name": "Free diagnosis",
            "description": "",
            "price_cents": None,
            "category": None,
            "media": None,
        }
    ]


async def test_offerings_can_be_edited_and_retired(
    client: httpx.AsyncClient, superuser_conn: Any
) -> None:
    headers, tenant_id = await _signup(client)
    other_headers, _other_tenant_id = await _signup(client)
    slug = (await client.get("/api/business/page", headers=headers)).json()["slug"]
    created = await client.post(
        "/api/business/offerings",
        json={"name": "Battery replacement", "price_dollars": "60"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    offering_id = created.json()["id"]
    assert created.json()["price_cents"] == 6000

    catalog_document = await superuser_conn.fetchrow(
        "select id, status from documents where tenant_id = $1 and doc_type = 'catalog'", tenant_id
    )
    assert catalog_document is not None
    assert catalog_document["status"] == "ready"
    assert (
        await superuser_conn.fetchval(
            "select count(*) from knowledge_chunks where document_id = $1", catalog_document["id"]
        )
    ) == 1

    updated = await client.patch(
        f"/api/business/offerings/{offering_id}",
        json={"description": "For compatible devices.", "price_dollars": "65.25"},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["description"] == "For compatible devices."
    assert updated.json()["price_cents"] == 6525

    forbidden = await client.delete(f"/api/business/offerings/{offering_id}", headers=other_headers)
    assert forbidden.status_code == 404

    retired = await client.delete(f"/api/business/offerings/{offering_id}", headers=headers)
    assert retired.status_code == 204

    # Retired, not deleted: the owner's list and the storefront both drop it,
    # the row stays so a past quote referring to it still resolves, and the
    # projection the agent searches loses its last document.
    assert (await client.get("/api/business/offerings", headers=headers)).json() == []
    assert (await client.get(f"/api/public/tenant/{slug}/storefront")).json()["offerings"] == []
    assert (
        await superuser_conn.fetchval(
            "select active from offerings where id = $1", uuid.UUID(offering_id)
        )
    ) is False
    assert (
        await superuser_conn.fetchval(
            "select count(*) from documents where tenant_id = $1 and doc_type = 'catalog'",
            tenant_id,
        )
    ) == 0


async def test_a_non_image_cover_is_refused(client: httpx.AsyncClient) -> None:
    headers, _ = await _signup(client)
    response = await client.put(
        "/api/business/cover",
        files={"file": ("menu.pdf", b"%PDF-1.4", "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 415


async def test_an_oversized_cover_is_refused(client: httpx.AsyncClient) -> None:
    """The cap is what a Postgres row should carry. The client resizes before
    sending; this is the backstop for a client that does not."""
    headers, _ = await _signup(client)
    response = await client.put(
        "/api/business/cover",
        files={"file": ("big.png", b"\x89PNG" + b"\x00" * (2 * 1024 * 1024), "image/png")},
        headers=headers,
    )
    assert response.status_code == 413


async def test_the_page_needs_a_session(client: httpx.AsyncClient) -> None:
    for method, path in (
        ("get", "/api/business/page"),
        ("get", "/api/business/cover"),
        ("delete", "/api/business/cover"),
    ):
        response = await getattr(client, method)(path)
        assert response.status_code == 401, f"{method} {path}"


async def _config_of(tenant_id: uuid.UUID) -> dict[str, Any]:
    import json

    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        raw = await conn.fetchval(
            "select config from tenant_config where tenant_id = $1", tenant_id
        )
    return json.loads(raw) if isinstance(raw, str) else (raw or {})


async def test_profile_patch_moves_both_keys_together(client: httpx.AsyncClient) -> None:
    """`config->profile` is what confirm writes; `config->onboarding.draft` is
    what the Booking page reads. They are allowed to differ already - a
    correction must not be the thing that makes them differ."""
    headers, tenant_id = await _signup(client)
    saved = await client.patch(
        "/api/business/profile",
        json={"abn": "51 824 753 556", "gst": "yes"},
        headers=headers,
    )
    assert saved.status_code == 200, saved.text
    # Stored as the digits, the way the interview stores them - the formatting
    # is the screen's job.
    assert saved.json() == {
        "abn": "51824753556",
        "gst": "yes",
        # W-9: the profile response carries the voice the assistant speaks in.
        # An owner who never reached the voice beat reads the default back.
        "customer_voice_preset": "warm_casual",
        "customer_voice_custom_style": "",
    }

    read_back = await client.get("/api/business/profile", headers=headers)
    assert read_back.json() == {
        "abn": "51824753556",
        "gst": "yes",
        "customer_voice_preset": "warm_casual",
        "customer_voice_custom_style": "",
    }

    config = await _config_of(tenant_id)
    assert config["profile"]["abn"] == "51824753556"
    assert config["onboarding"]["draft"]["abn"] == "51824753556"
    assert config["profile"]["gst"] == "yes"
    assert config["onboarding"]["draft"]["gst"] == "yes"


async def test_profile_patch_leaves_absent_fields_alone(client: httpx.AsyncClient) -> None:
    headers, _ = await _signup(client)
    await client.patch(
        "/api/business/profile", json={"abn": "51824753556", "gst": "yes"}, headers=headers
    )
    saved = await client.patch("/api/business/profile", json={"gst": "no"}, headers=headers)
    assert saved.json() == {
        "abn": "51824753556",
        "gst": "no",
        # W-9: the profile response carries the voice the assistant speaks in.
        # An owner who never reached the voice beat reads the default back.
        "customer_voice_preset": "warm_casual",
        "customer_voice_custom_style": "",
    }


async def test_a_cleared_abn_is_the_stated_no(client: httpx.AsyncClient) -> None:
    """Blank means "I do not have one", the same answer the interview's "No,
    not yet" chip leaves - not "never asked"."""
    headers, _ = await _signup(client)
    saved = await client.patch("/api/business/profile", json={"abn": "  "}, headers=headers)
    assert saved.json()["abn"] == "none"


@pytest.mark.parametrize("abn", ["123", "5182475355", "518247535567", "abc"])
async def test_an_abn_must_be_eleven_digits(client: httpx.AsyncClient, abn: str) -> None:
    headers, _ = await _signup(client)
    response = await client.patch("/api/business/profile", json={"abn": abn}, headers=headers)
    assert response.status_code == 422, response.text


async def test_gst_takes_only_yes_or_no(client: httpx.AsyncClient) -> None:
    headers, _ = await _signup(client)
    response = await client.patch("/api/business/profile", json={"gst": "maybe"}, headers=headers)
    assert response.status_code == 422


async def test_a_field_outside_the_editable_slice_is_refused(client: httpx.AsyncClient) -> None:
    """The rest of the profile is frozen at confirm. A request that thought
    otherwise hears so, instead of being quietly ignored."""
    headers, _ = await _signup(client)
    response = await client.patch(
        "/api/business/profile", json={"business_name": "Renamed Co"}, headers=headers
    )
    assert response.status_code == 422


async def test_the_profile_needs_a_session(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/business/profile")).status_code == 401
    assert (await client.patch("/api/business/profile", json={"gst": "no"})).status_code == 401


async def test_the_patch_leaves_the_rest_of_the_onboarding_record_alone(
    client: httpx.AsyncClient,
) -> None:
    """The draft lives inside the record that also holds `completed` and the
    transcript. Clobbering those would re-interview an owner who only wanted to
    fix their ABN."""
    import json

    headers, tenant_id = await _signup(client)
    record = {
        "version": 3,
        "draft": {"name": "Sam", "abn": "none"},
        "history": [{"role": "user", "content": "hi"}],
        "completed": True,
    }
    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        await conn.execute(
            "update tenant_config set config = jsonb_set(config, '{onboarding}', $2::jsonb, true) "
            "where tenant_id = $1",
            tenant_id,
            json.dumps(record),
        )

    await client.patch("/api/business/profile", json={"abn": "51824753556"}, headers=headers)

    onboarding = (await _config_of(tenant_id))["onboarding"]
    assert onboarding["completed"] is True
    assert onboarding["history"] == [{"role": "user", "content": "hi"}]
    assert onboarding["draft"]["name"] == "Sam"
    assert onboarding["draft"]["abn"] == "51824753556"
