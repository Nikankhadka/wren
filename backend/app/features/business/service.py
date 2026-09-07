"""E-6: persistence for the Booking page - the links and the cover photo."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.features.business.media import Cloudinary, MediaUploadError, UploadedMedia, classify_url
from app.features.business.offering_candidates import normalize_name
from app.features.tenants.service import invalidate_slug_cache
from app.ingestion.pipeline import ingest_offerings
from app.llm.dependency import get_llm_provider
from app.llm.embedder import Embedder
from app.llm.provider import LLMProvider
from app.shared import db
from app.shared.config import get_settings
from app.shared.voice import voice_from_config

# The four places a small business is already found. Fixed, because the
# prototype's row is four tiles - an open-ended list is a different screen.
LINK_KEYS = ("website", "google", "facebook", "instagram")

COVER_KIND = "cover"


class _CategorySuggestion(BaseModel):
    category: str | None = Field(default=None, max_length=80)


async def _suggest_category(
    *, name: str, description: str, preferred: list[str], provider: LLMProvider
) -> str | None:
    try:
        result = await asyncio.wait_for(
            provider.extract(
                system_prompt=(
                    "Suggest one short, business-agnostic catalogue category. "
                    "Return null if uncertain. Prefer one of these existing categories "
                    "when suitable: "
                    f"{', '.join(preferred) or 'none'}. Never include prices."
                ),
                user_input=f"Name: {name}\nDescription: {description}",
                schema=_CategorySuggestion,
            ),
            timeout=4,
        )
    except Exception:
        return None
    value = (result.category or "").strip()
    return value or None


async def list_offerings(*, tenant_id: UUID, active_only: bool = False) -> list[dict[str, Any]]:
    """The owner's structured offerings, in the order they appear on the page.

    ``position`` is the owner's own ordering; ``created_at`` then ``id`` break
    ties so a list that has never been reordered still reads oldest-first
    rather than arbitrarily.
    """
    active_filter = "and active" if active_only else ""
    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        rows = await conn.fetch(
            "select o.id, o.name, o.description, o.price_cents, o.category, o.active, o.position, "
            "m.type as media_type, m.provider as media_provider, m.url as media_url, m.poster_url "
            "from offerings o left join tenant_media m on m.offering_id = o.id "
            "and m.role = 'offering' "
            f"where o.tenant_id = $1 {active_filter} order by o.position, o.created_at, o.id",  # noqa: S608
            tenant_id,
        )
    result = []
    for row in rows:
        item = dict(row)
        media_url = item.pop("media_url", None)
        if media_url:
            item["media"] = {
                "type": item.pop("media_type"),
                "provider": item.pop("media_provider"),
                "url": media_url,
                "poster_url": item.pop("poster_url", None),
            }
        else:
            for key in ("media_type", "media_provider", "poster_url"):
                item.pop(key, None)
            item["media"] = None
        result.append(item)
    return result


async def create_offering(
    *,
    tenant_id: UUID,
    name: str,
    description: str,
    price_cents: int | None,
    embedder: Embedder,
    category: str | None = None,
) -> dict[str, Any]:
    """Create one offering at the end of the list, then rebuild its projection."""
    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        rows = await create_offerings_batch(
            conn=conn,
            tenant_id=tenant_id,
            offerings=[
                {
                    "name": name,
                    "description": description,
                    "price_cents": price_cents,
                    "category": category,
                }
            ],
            embedder=embedder,
        )
    if not rows:
        raise ValueError("offering name already exists")
    return rows[0]


async def create_offerings_batch(
    *,
    conn: db.AppConnection,
    tenant_id: UUID,
    offerings: list[dict[str, Any]],
    embedder: Embedder,
) -> list[dict[str, Any]]:
    """Insert new active offerings in stable order and rebuild the catalog once."""
    existing_rows = await conn.fetch(
        "select name from offerings where tenant_id = $1 and active", tenant_id
    )
    existing = {normalize_name(str(row["name"])) for row in existing_rows}
    existing_categories = sorted(
        {
            str(row["category"]).strip()
            for row in await conn.fetch(
                "select distinct category from offerings "
                "where tenant_id=$1 and category is not null",
                tenant_id,
            )
        }
    )
    settings = get_settings()
    category_provider = (
        get_llm_provider()
        if settings.environment == "production"
        and (settings.llm_api_key or settings.azure_openai_api_key)
        else None
    )
    position = await conn.fetchval(
        "select coalesce(max(position) + 1, 0) from offerings where tenant_id = $1", tenant_id
    )
    rows: list[dict[str, Any]] = []
    for item in offerings:
        name = str(item.get("name", "")).strip()
        key = normalize_name(name)
        if not name or key in existing:
            continue
        category = str(item.get("category") or "").strip() or None
        if category is None and category_provider is not None:
            category = await _suggest_category(
                name=name,
                description=str(item.get("description", "")),
                preferred=existing_categories,
                provider=category_provider,
            )
        row = await conn.fetchrow(
            "insert into offerings (tenant_id, name, description, price_cents, category, position) "
            "values ($1, $2, $3, $4, $5, $6) returning id, name, description, price_cents, "
            "category, active, "
            "position",
            tenant_id,
            name,
            str(item.get("description", "")),
            item.get("price_cents"),
            category,
            position,
        )
        if row is not None:
            rows.append(dict(row))
            existing.add(key)
            position += 1
    if rows:
        await ingest_offerings(conn, tenant_id=tenant_id, embedder=embedder)
    return rows


async def reconcile_offerings_batch(
    *,
    conn: db.AppConnection,
    tenant_id: UUID,
    offerings: list[dict[str, Any]],
    embedder: Embedder,
) -> None:
    """Apply the reviewed catalog in one transaction and rebuild it once."""
    keys: set[str] = set()
    for item in offerings:
        key = normalize_name(str(item.get("name", "")))
        if not key or key in keys:
            raise ValueError("duplicate offering name")
        keys.add(key)

    existing_rows = await conn.fetch(
        "select id, name from offerings where tenant_id = $1 and active", tenant_id
    )
    existing = {normalize_name(str(row["name"])): row for row in existing_rows}
    position = await conn.fetchval(
        "select coalesce(max(position) + 1, 0) from offerings where tenant_id = $1", tenant_id
    )
    changed = False
    for item in offerings:
        name = str(item.get("name", "")).strip()
        key = normalize_name(name)
        values = (name, str(item.get("description", "")), item.get("price_cents"))
        row = existing.get(key)
        if row is not None:
            await conn.execute(
                "update offerings set name = $3, description = $4, price_cents = $5 "
                "where tenant_id = $1 and id = $2",
                tenant_id,
                row["id"],
                *values,
            )
        else:
            inserted = await conn.fetchrow(
                "insert into offerings (tenant_id, name, description, price_cents, position) "
                "values ($1, $2, $3, $4, $5) returning id, name",
                tenant_id,
                *values,
                position,
            )
            if inserted is not None:
                existing[key] = inserted
                position += 1
        changed = True
    if changed:
        await ingest_offerings(conn, tenant_id=tenant_id, embedder=embedder)
        catalog = await conn.fetchrow(
            "select status, error from documents "
            "where tenant_id = $1 and doc_type = 'catalog' "
            "order by uploaded_at desc limit 1",
            tenant_id,
        )
        if catalog is not None and catalog["status"] == "failed":
            raise ValueError(str(catalog["error"] or "catalog rebuild failed"))


async def update_offering(
    *,
    tenant_id: UUID,
    offering_id: UUID,
    updates: dict[str, Any],
    embedder: Embedder,
) -> dict[str, Any] | None:
    """Update an offering owned by this tenant and rebuild its projection.

    ``updates`` keys are column names from the API layer's fixed allowlist, not
    caller-supplied strings - the interpolation below is safe for that reason
    and for no other. It is never empty: the route refuses an empty patch with
    a 422 before reaching here.
    """
    columns = tuple(updates)
    assignments = ", ".join(f"{column} = ${index}" for index, column in enumerate(columns, start=3))
    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        row = await conn.fetchrow(
            f"update offerings set {assignments} "  # noqa: S608 - fixed API allowlist
            "where tenant_id = $1 and id = $2 "
            "returning id, name, description, price_cents, category, active, position",
            tenant_id,
            offering_id,
            *(updates[column] for column in columns),
        )
        if row is not None:
            await ingest_offerings(conn, tenant_id=tenant_id, embedder=embedder)
    return dict(row) if row is not None else None


async def deactivate_offering(*, tenant_id: UUID, offering_id: UUID, embedder: Embedder) -> bool:
    """Retire an offering by clearing ``active`` rather than deleting the row.

    The row is what a past quote or order refers to by id, so deleting it would
    strand that history; ``active`` exists on the table for exactly this, and
    every reader (the projection, the storefront, the booking page) already
    filters on it. Keeping the row also keeps its ``updated_at``, which is what
    ``knowledge_version`` reads - a hard delete would leave nothing behind for
    the cache to notice.
    """
    return (
        await update_offering(
            tenant_id=tenant_id,
            offering_id=offering_id,
            updates={"active": False},
            embedder=embedder,
        )
        is not None
    )


async def read_links(*, tenant_id: UUID) -> dict[str, str]:
    """The saved links, keyed by platform. Absent keys mean "not added yet"."""
    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        raw = await conn.fetchval("select brand from tenant_config where tenant_id = $1", tenant_id)
    brand = json.loads(raw) if isinstance(raw, str) else (raw or {})
    links = brand.get("links") if isinstance(brand, dict) else None
    if not isinstance(links, dict):
        return {}
    return {key: str(links[key]) for key in LINK_KEYS if links.get(key)}


async def write_links(*, tenant_id: UUID, links: dict[str, str]) -> dict[str, str]:
    """Replace the links object. An empty string removes one.

    Written into ``brand`` rather than a table of its own: four short strings
    that every surface reading the tenant already fetches, and `brand` is the
    column the public tenant lookup returns, which is where the customer-facing
    page will read them from next.
    """
    kept = {key: value.strip() for key, value in links.items() if key in LINK_KEYS}
    kept = {key: value for key, value in kept.items() if value}
    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        await conn.execute(
            "update tenant_config set brand = jsonb_set(brand, '{links}', $2::jsonb, true) "
            "where tenant_id = $1",
            tenant_id,
            json.dumps(kept),
        )
    return kept


async def write_cover(
    *, tenant_id: UUID, mime: str, data: bytes, cloudinary: Cloudinary | None = None
) -> None:
    """Store this tenant's cover, replacing any it already has.

    One statement, so two uploads racing (a double-tapped picker, a retried
    request) resolve to one winner rather than one of them being dropped on the
    primary key while the owner is told it succeeded.
    """
    if cloudinary is not None:
        if cloudinary.is_configured:
            uploaded = await cloudinary.upload(
                data=data, resource_type="image", folder=f"tenants/{tenant_id}/cover"
            )
            await _replace_media(
                tenant_id=tenant_id,
                offering_id=None,
                role=COVER_KIND,
                media=uploaded,
                cloudinary=cloudinary,
            )
            return
        if get_settings().environment == "production":
            raise MediaUploadError("Cloudinary is not configured")
    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        await conn.execute(
            "insert into tenant_assets (tenant_id, kind, mime, bytes) values ($1, $2, $3, $4) "
            "on conflict (tenant_id, kind) do update set mime = excluded.mime, "
            "bytes = excluded.bytes, updated_at = now()",
            tenant_id,
            COVER_KIND,
            mime,
            data,
        )


async def read_cover(*, tenant_id: UUID) -> tuple[str, bytes, Any] | None:
    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        row = await conn.fetchrow(
            "select mime, bytes, updated_at from tenant_assets where tenant_id = $1 and kind = $2",
            tenant_id,
            COVER_KIND,
        )
    if row is None:
        return None
    return row["mime"], bytes(row["bytes"]), row["updated_at"]


async def read_cover_url(*, tenant_id: UUID, role: str) -> str | None:
    context_role = "customer" if role == COVER_KIND else "tenant_admin"
    async with db.tenant_context(tenant_id, context_role) as conn:
        value = await conn.fetchval(
            "select url from tenant_media where tenant_id=$1 and role=$2 and offering_id is null",
            tenant_id,
            role,
        )
        return str(value) if value is not None else None


async def has_cover(*, tenant_id: UUID) -> bool:
    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        return bool(
            await conn.fetchval(
                "select 1 from tenant_assets where tenant_id = $1 and kind = $2 "
                "union all "
                "select 1 from tenant_media where tenant_id = $1 and role = $2 limit 1",
                tenant_id,
                COVER_KIND,
            )
        )


async def delete_cover(*, tenant_id: UUID) -> None:
    cloudinary = Cloudinary()
    if cloudinary.is_configured:
        await delete_media(
            tenant_id=tenant_id, offering_id=None, role=COVER_KIND, cloudinary=cloudinary
        )
        async with db.tenant_context(tenant_id, "tenant_admin") as conn:
            await conn.execute(
                "delete from tenant_assets where tenant_id = $1 and kind = $2",
                tenant_id,
                COVER_KIND,
            )
        return
    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        if await conn.fetchval(
            "select 1 from tenant_media where tenant_id = $1 and role = $2",
            tenant_id,
            COVER_KIND,
        ):
            raise MediaUploadError("Cloudinary is not configured")
        await conn.execute(
            "delete from tenant_assets where tenant_id = $1 and kind = $2",
            tenant_id,
            COVER_KIND,
        )


async def write_storefront(*, tenant_id: UUID, about: str | None = None) -> dict[str, Any]:
    """Merge editable storefront sections into the brand configuration.

    These are small presentation fields, not knowledge. Keeping them together
    makes the owner page a direct representation of the public page without a
    separate page-builder schema or drag-and-drop system.
    """
    patch: dict[str, Any] = {}
    if about is not None:
        patch["about"] = about
    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        await conn.execute(
            "update tenant_config set brand = jsonb_set(brand, '{storefront}', "
            "coalesce(brand->'storefront', '{}'::jsonb) || $2::jsonb, true), updated_at = now() "
            "where tenant_id = $1",
            tenant_id,
            json.dumps(patch),
        )
    return await read_storefront_sections(tenant_id=tenant_id)


async def read_storefront_sections(*, tenant_id: UUID) -> dict[str, Any]:
    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        raw = await conn.fetchval(
            "select brand -> 'storefront' from tenant_config where tenant_id = $1", tenant_id
        )
    parsed = json.loads(raw) if isinstance(raw, str) else (raw or {})
    if not isinstance(parsed, dict):
        return {"about": ""}
    about = parsed.get("about")
    return {
        "about": about.strip() if isinstance(about, str) else "",
    }


def resolve_profile(config: dict[str, Any]) -> dict[str, Any]:
    """The business profile as any presentation surface must read it.

    ``config->profile`` is what confirm writes; ``config->onboarding.draft`` is
    what an interview still in flight has. One resolution order, in one place,
    so the owner's preview and the customer's page cannot read different halves
    of the pair and disagree about the same business.
    """
    profile = config.get("profile") or (config.get("onboarding") or {}).get("draft") or {}
    return profile if isinstance(profile, dict) else {}


def profile_tagline(profile: dict[str, Any]) -> str | None:
    """The prototype's one-line subtitle: what the business does, then when it
    is open. Either half may be missing - a business that never answered the
    hours beat gets the shorter sentence rather than a dangling separator."""
    kept = [part for key in ("services", "hours") if (part := str(profile.get(key, "")).strip())]
    return " · ".join(kept) if kept else None


def display_name(
    *, brand: dict[str, Any], business_name: Any, profile: dict[str, Any], fallback: Any
) -> str:
    """What to call this business, most specific source first: the brand
    override, the name captured at go-live, the profile, then the tenant's
    signup name - which always exists, so this always returns something."""
    return str(
        (brand.get("display_name") if isinstance(brand, dict) else None)
        or business_name
        or str(profile.get("business_name", "")).strip()
        or fallback
    )


async def read_profile_for_display(*, tenant_id: UUID) -> dict[str, Any]:
    """``resolve_profile`` against the owner's own tenant_config."""
    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        raw = await conn.fetchval(
            "select config from tenant_config where tenant_id = $1", tenant_id
        )
    config = json.loads(raw) if isinstance(raw, str) else (raw or {})
    return resolve_profile(config if isinstance(config, dict) else {})


async def read_public_storefront(*, tenant_id: UUID) -> dict[str, Any]:
    """Read only the public presentation fields under the customer context."""
    async with db.tenant_context(tenant_id, "customer") as conn:
        tenant = await conn.fetchrow(
            "select t.name, t.business_name, tc.brand, tc.config "
            "from tenants t join tenant_config tc on tc.tenant_id = t.id where t.id = $1",
            tenant_id,
        )
        offerings = await conn.fetch(
            "select id, name, description, price_cents, category from offerings "
            "where tenant_id = $1 and active order by position, created_at, id",
            tenant_id,
        )
        cover = await conn.fetchval(
            "select 1 from tenant_assets where tenant_id = $1 and kind = $2",
            tenant_id,
            COVER_KIND,
        )
        media_rows = await conn.fetch(
            "select offering_id, role, type, provider, url, poster_url from tenant_media "
            "where tenant_id = $1 order by created_at, id",
            tenant_id,
        )
    if tenant is None:
        raise LookupError("tenant not found")
    brand_raw = tenant["brand"]
    config_raw = tenant["config"]
    brand = json.loads(brand_raw) if isinstance(brand_raw, str) else (brand_raw or {})
    config = json.loads(config_raw) if isinstance(config_raw, str) else (config_raw or {})
    if not isinstance(brand, dict):
        brand = {}
    if not isinstance(config, dict):
        config = {}
    profile = resolve_profile(config)
    media_by_offering = {
        str(row["offering_id"]): dict(row) for row in media_rows if row["offering_id"]
    }
    cover_media = next((dict(row) for row in media_rows if row["role"] == COVER_KIND), None)
    published_offerings = []
    for row in offerings:
        item = dict(row)
        item["media"] = media_by_offering.get(str(item["id"]))
        published_offerings.append(item)
    return {
        "name": display_name(
            brand=brand,
            business_name=tenant["business_name"],
            profile=profile,
            fallback=tenant["name"],
        ),
        "tagline": profile_tagline(profile),
        "links": {
            key: value
            for key, value in (brand.get("links") or {}).items()
            if key in LINK_KEYS and isinstance(value, str) and value
        },
        "offerings": published_offerings,
        "has_cover": bool(cover or cover_media),
        "cover_url": cover_media.get("url") if cover_media else None,
    }


async def _replace_media(
    *,
    tenant_id: UUID,
    offering_id: UUID | None,
    role: str,
    media: UploadedMedia,
    cloudinary: Cloudinary,
) -> None:
    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        previous = await conn.fetchrow(
            "select id, public_id, type, provider, url, poster_url from tenant_media "
            "where tenant_id = $1 and role = $2 "
            "and (($3::uuid is null and offering_id is null) or offering_id = $3) "
            "for update",
            tenant_id,
            role,
            offering_id,
        )
        if previous:
            await conn.execute(
                "update tenant_media set type=$4, provider=$5, url=$6, public_id=$7, "
                "poster_url=$8, updated_at=now() where tenant_id=$1 and role=$2 "
                "and (($3::uuid is null and offering_id is null) or offering_id=$3)",
                tenant_id,
                role,
                offering_id,
                media.type,
                media.provider,
                media.url,
                media.public_id,
                media.poster_url,
            )
        else:
            await conn.execute(
                "insert into tenant_media (tenant_id, offering_id, role, type, provider, url, "
                "public_id, poster_url) "
                "values ($1,$2,$3,$4,$5,$6,$7,$8)",
                tenant_id,
                offering_id,
                role,
                media.type,
                media.provider,
                media.url,
                media.public_id,
                media.poster_url,
            )
    if previous and previous["public_id"] and previous["provider"] == "cloudinary":
        try:
            await cloudinary.delete(
                public_id=str(previous["public_id"]), resource_type=str(previous["type"])
            )
        except MediaUploadError:
            async with db.tenant_context(tenant_id, "tenant_admin") as conn:
                await conn.execute(
                    "update tenant_media set type=$2, provider=$3, url=$4, public_id=$5, "
                    "poster_url=$6, updated_at=now() where id=$1 and url=$7",
                    previous["id"],
                    previous["type"],
                    previous["provider"],
                    previous["url"],
                    previous["public_id"],
                    previous["poster_url"],
                    media.url,
                )
            if media.public_id and media.provider == "cloudinary":
                try:
                    await cloudinary.delete(
                        public_id=str(media.public_id), resource_type=str(media.type)
                    )
                except MediaUploadError:
                    pass
            raise


async def delete_media(
    *, tenant_id: UUID, offering_id: UUID | None, role: str, cloudinary: Cloudinary
) -> bool:
    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        previous = await conn.fetchrow(
            "select id, public_id, type, provider, url from tenant_media "
            "where tenant_id=$1 and role=$2 "
            "and (($3::uuid is null and offering_id is null) or offering_id=$3) "
            "for update",
            tenant_id,
            role,
            offering_id,
        )
    if previous is None:
        return False
    if previous["public_id"] and previous["provider"] == "cloudinary":
        await cloudinary.delete(
            public_id=str(previous["public_id"]), resource_type=str(previous["type"])
        )
    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        await conn.execute(
            "delete from tenant_media where tenant_id=$1 and id=$2 "
            "and public_id is not distinct from $3 and url=$4",
            tenant_id,
            previous["id"],
            previous["public_id"],
            previous["url"],
        )
    return True


async def set_offering_media(
    *, tenant_id: UUID, offering_id: UUID, value: bytes | str, mime: str | None = None
) -> dict[str, Any]:
    cloudinary = Cloudinary()
    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        exists = await conn.fetchval(
            "select 1 from offerings where tenant_id=$1 and id=$2", tenant_id, offering_id
        )
    if not exists:
        raise LookupError("offering not found")
    classified = classify_url(value) if isinstance(value, str) else None
    if classified:
        media = UploadedMedia(type=classified[0], provider=classified[1], url=str(value))
    else:
        if not cloudinary.is_configured:
            raise MediaUploadError("Cloudinary is not configured")
        resource_type = "video" if (mime or "").startswith("video/") else "auto"
        media = await cloudinary.upload(
            data=value,
            resource_type=resource_type,
            folder=f"tenants/{tenant_id}/offerings/{offering_id}",
        )
    await _replace_media(
        tenant_id=tenant_id,
        offering_id=offering_id,
        role="offering",
        media=media,
        cloudinary=cloudinary,
    )
    return media.__dict__


async def read_public_cover(*, tenant_id: UUID) -> tuple[str, bytes, Any] | None:
    async with db.tenant_context(tenant_id, "customer") as conn:
        row = await conn.fetchrow(
            "select mime, bytes, updated_at from tenant_assets where tenant_id = $1 and kind = $2",
            tenant_id,
            COVER_KIND,
        )
    if row is None:
        return None
    return row["mime"], bytes(row["bytes"]), row["updated_at"]


# O-9: the slice of the profile an owner can correct after go-live. The rest of
# the profile is written once, at confirm, and stays frozen - the ticket says
# why, and a settings tree that edits all of it is not being built.
PROFILE_FIELDS = ("abn", "gst")

# W-9: how the public assistant sounds. Editable here beside the ABN, but kept
# at `config->customer_voice` rather than in the profile object, because that is
# the one shape `app/shared/voice.py` reads and the voice beat's confirm writes.
VOICE_FIELDS = ("customer_voice_preset", "customer_voice_custom_style")
EDITABLE_FIELDS = PROFILE_FIELDS + VOICE_FIELDS


async def read_profile(*, tenant_id: UUID) -> dict[str, str]:
    """The editable profile fields, empty string where nothing was captured.

    Reads `config->profile` (what confirm writes) and falls back per field to
    `config->onboarding.draft` (what an interview in flight has), so a value is
    shown whichever half of the pair holds it.
    """
    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        raw = await conn.fetchval(
            "select config from tenant_config where tenant_id = $1", tenant_id
        )
    config = json.loads(raw) if isinstance(raw, str) else (raw or {})
    profile = config.get("profile") or {}
    draft = (config.get("onboarding") or {}).get("draft") or {}
    fields = {key: str(profile.get(key) or draft.get(key) or "") for key in PROFILE_FIELDS}
    # The voice is read through the same normalizer the customer contract uses,
    # so the editor opens on the voice the assistant is actually speaking in -
    # including the default a tenant who never reached the voice beat resolves to.
    voice = voice_from_config(config)
    fields["customer_voice_preset"] = voice.preset
    fields["customer_voice_custom_style"] = voice.custom_style
    return fields


async def write_profile(*, tenant_id: UUID, fields: dict[str, str]) -> dict[str, str]:
    """Merge `fields` into the places each of them is kept.

    `config->profile` is what confirm writes and what the E-5 spec names;
    `config->onboarding.draft` is what the Booking page reads. They are already
    allowed to diverge - this does not add a second way for them to, so one
    statement moves both. Each object is rebuilt from itself with `||` so a
    tenant missing either key gains it rather than silently keeping the old
    value. The voice is written whole to `config->customer_voice`, the shape
    `app/shared/voice.py` reads, so the two never half-agree.

    Both writes bump `tenant_config.updated_at`, which `knowledge_version`
    already turns into an agent-prompt cache bust. The customer surface's own
    60-second slug cache is a separate path, so it is dropped here too - without
    that, a saved change waits out the cache before a customer sees it.
    """
    profile_patch = {key: value for key, value in fields.items() if key in PROFILE_FIELDS}
    voice = (
        {
            "preset": fields["customer_voice_preset"],
            "custom_style": fields.get("customer_voice_custom_style") or None,
        }
        if "customer_voice_preset" in fields
        else None
    )
    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        if profile_patch:
            await conn.execute(
                "update tenant_config set config = jsonb_set("
                "  jsonb_set(config, '{profile}', "
                "    coalesce(config->'profile', '{}'::jsonb) || $2::jsonb, true), "
                "  '{onboarding}', "
                "    coalesce(config->'onboarding', '{}'::jsonb) || jsonb_build_object('draft', "
                "      coalesce(config->'onboarding'->'draft', '{}'::jsonb) || $2::jsonb), true"
                "), updated_at = now() where tenant_id = $1",
                tenant_id,
                json.dumps(profile_patch),
            )
        if voice is not None:
            await conn.execute(
                "update tenant_config set config = jsonb_set(config, '{customer_voice}', "
                "$2::jsonb, true), updated_at = now() where tenant_id = $1",
                tenant_id,
                json.dumps(voice),
            )
        slug = await conn.fetchval("select slug from tenants where id = $1", tenant_id)
    if slug:
        invalidate_slug_cache(str(slug))
    return await read_profile(tenant_id=tenant_id)
