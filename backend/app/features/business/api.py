"""E-6/M-1/M-4: the Business page - the business as a customer finds it.

One read for the whole screen, a write for the four links, the cover photo in
and out, the owner's offerings, and (O-9)
the two profile fields that stay correctable after go-live.

The money rule is held by construction on every path here: no model runs on
any of them, and an offering's price is the owner's own typed value, validated
as a decimal and stored as integer cents - never inferred, rounded or computed.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Annotated
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.features.business import controller, service
from app.features.business.media import Cloudinary, MediaUploadError, OfferingMedia
from app.llm.dependency import get_embedder_dependency
from app.llm.embedder import Embedder
from app.onboarding.beats import NO_ABN
from app.shared import auth
from app.shared.voice import CUSTOM_VOICE, CUSTOM_VOICE_MAX, VOICE_PRESETS

router = APIRouter(prefix="/api/business", tags=["business"])

# One cover photo, resized client-side before it is sent. The cap is what a row
# should carry, not what an image could be.
MAX_COVER_BYTES = 2 * 1024 * 1024
ALLOWED_COVER_MIME = ("image/jpeg", "image/png", "image/webp")


class BookingPageOffering(BaseModel):
    name: str
    description: str
    price_cents: int | None
    category: str | None = None
    media: OfferingMedia | None = None


class BookingPageResponse(BaseModel):
    slug: str
    name: str
    tagline: str | None
    links: dict[str, str]
    has_cover: bool
    cover_url: str | None = None
    offerings: list[BookingPageOffering]


class LinksUpdate(BaseModel):
    """The four link slots. An empty string clears one; an absent key leaves it."""

    links: dict[str, str] = Field(default_factory=dict)

    @field_validator("links")
    @classmethod
    def _validate(cls, value: dict[str, str]) -> dict[str, str]:
        for key, url in value.items():
            if key not in service.LINK_KEYS:
                raise ValueError(f"unknown link {key!r}")
            if not url.strip():
                continue
            parsed = urlparse(url.strip())
            # These addresses are rendered as links a customer clicks, so the
            # scheme allowlist is the guard against a javascript: or data: URL
            # arriving through the owner's own settings.
            if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
                raise ValueError(f"{key} must be an absolute http:// or https:// URL")
        return value


_MAX_OFFERING_DOLLARS = Decimal("1000000")


def _offering_price(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("price is not a valid decimal amount") from exc
    if not amount.is_finite():
        raise ValueError("price must be finite")
    if amount < 0:
        raise ValueError("price must not be negative")
    if amount > _MAX_OFFERING_DOLLARS:
        raise ValueError(f"price must not exceed {_MAX_OFFERING_DOLLARS}")
    if amount != amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP):
        raise ValueError("price must have at most 2 decimal places")
    return amount


def _price_cents(amount: Decimal | None) -> int | None:
    if amount is None:
        return None
    return int((amount * 100).to_integral_value(rounding=ROUND_HALF_UP))


class OfferingResponse(BaseModel):
    id: UUID
    name: str
    description: str
    price_cents: int | None
    category: str | None = None
    media: OfferingMedia | None = None


class OfferingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    price_dollars: Decimal | None = None
    category: str | None = Field(default=None, max_length=80)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        if not (normalized := value.strip()):
            raise ValueError("name must not be blank")
        return normalized

    @field_validator("description")
    @classmethod
    def _description(cls, value: str) -> str:
        return value.strip()

    @field_validator("price_dollars", mode="before")
    @classmethod
    def _price(cls, value: object) -> Decimal | None:
        return _offering_price(value)


class OfferingUpdate(BaseModel):
    """A partial edit: an absent key means "leave this alone".

    Only ``price_dollars`` reads an explicit null as a value - it clears the
    published price. ``name`` and ``description`` are ``not null`` columns, so
    a null for either is a 422 here rather than a constraint violation at the
    UPDATE; absence, not null, is how a field is left unchanged.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description: str | None = None
    price_dollars: Decimal | None = None
    category: str | None = Field(default=None, max_length=80)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str:
        if value is None or not (normalized := value.strip()):
            raise ValueError("name must not be blank")
        return normalized

    @field_validator("description")
    @classmethod
    def _description(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("description must not be null; use an empty string to clear it")
        return value.strip()

    @field_validator("price_dollars", mode="before")
    @classmethod
    def _price(cls, value: object) -> Decimal | None:
        return _offering_price(value)

    def updates(self) -> dict[str, object]:
        updates: dict[str, object] = {}
        if "name" in self.model_fields_set:
            updates["name"] = self.name
        if "description" in self.model_fields_set:
            updates["description"] = self.description
        if "price_dollars" in self.model_fields_set:
            updates["price_cents"] = _price_cents(self.price_dollars)
        if "category" in self.model_fields_set:
            updates["category"] = self.category.strip() if self.category else None
        return updates


@router.get("/page", response_model=BookingPageResponse)
async def get_booking_page(
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_owner)],
) -> BookingPageResponse:
    try:
        return BookingPageResponse(**await controller.booking_page(tenant_id=admin.tenant_id))
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="tenant not found"
        ) from exc


@router.patch("/links", response_model=dict[str, str])
async def patch_links(
    body: LinksUpdate,
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_owner)],
) -> dict[str, str]:
    current = await service.read_links(tenant_id=admin.tenant_id)
    current.update(body.links)
    return await service.write_links(tenant_id=admin.tenant_id, links=current)


@router.get("/offerings", response_model=list[OfferingResponse])
async def list_offerings(
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_owner)],
) -> list[OfferingResponse]:
    rows = await service.list_offerings(tenant_id=admin.tenant_id, active_only=True)
    return [OfferingResponse.model_validate(row) for row in rows]


@router.post(
    "/offerings",
    response_model=OfferingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_offering(
    body: OfferingCreate,
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_owner)],
    embedder: Annotated[Embedder, Depends(get_embedder_dependency)],
) -> OfferingResponse:
    return OfferingResponse.model_validate(
        await service.create_offering(
            tenant_id=admin.tenant_id,
            name=body.name,
            description=body.description,
            price_cents=_price_cents(body.price_dollars),
            category=body.category.strip() if body.category else None,
            embedder=embedder,
        )
    )


@router.patch("/offerings/{offering_id}", response_model=OfferingResponse)
async def patch_offering(
    offering_id: UUID,
    body: OfferingUpdate,
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_owner)],
    embedder: Annotated[Embedder, Depends(get_embedder_dependency)],
) -> OfferingResponse:
    updates = body.updates()
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="no fields to update"
        )
    row = await service.update_offering(
        tenant_id=admin.tenant_id,
        offering_id=offering_id,
        updates=updates,
        embedder=embedder,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="offering not found")
    return OfferingResponse.model_validate(row)


@router.delete("/offerings/{offering_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_offering(
    offering_id: UUID,
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_owner)],
    embedder: Annotated[Embedder, Depends(get_embedder_dependency)],
) -> Response:
    if not await service.deactivate_offering(
        tenant_id=admin.tenant_id, offering_id=offering_id, embedder=embedder
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="offering not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class BusinessProfile(BaseModel):
    """The editable profile, every field present.

    The response the console reads and the type the frontend generates from, so
    each field is a plain string rather than an optional: a value that was never
    captured is the empty string, which is what the screens already render.
    """

    abn: str
    gst: str
    customer_voice_preset: str
    customer_voice_custom_style: str


class ProfileUpdate(BaseModel):
    """The ABN and its GST answer, and how the public assistant sounds - the
    slice of the profile that stays correctable after go-live.

    Extra keys are refused rather than ignored: the rest of the profile is
    frozen at confirm, and a request that thought otherwise should hear so.
    """

    model_config = ConfigDict(extra="forbid")

    abn: str | None = None
    gst: str | None = None
    customer_voice_preset: str | None = None
    customer_voice_custom_style: str | None = None

    def normalized(self) -> dict[str, str]:
        """The fields as they are stored, or a ValueError an owner can read.

        Not field validators: pydantic prefixes those with "Value error," and
        this message is rendered verbatim under the field the owner is typing
        in.
        """
        fields: dict[str, str] = {}
        if self.abn is not None:
            fields["abn"] = _normalize_abn(self.abn)
        if self.gst is not None:
            gst = self.gst.strip().lower()
            if gst not in ("yes", "no"):
                raise ValueError("GST is either yes or no.")
            fields["gst"] = gst
        if self.customer_voice_preset is not None or self.customer_voice_custom_style is not None:
            fields.update(
                _normalize_voice(self.customer_voice_preset, self.customer_voice_custom_style)
            )
        return fields


def _normalize_voice(preset: str | None, custom_style: str | None) -> dict[str, str]:
    """The voice as `app/shared/voice.py` stores it, or a ValueError.

    Both halves are always written together: a description belongs to `custom`
    alone, so choosing a preset clears whatever description was there rather
    than leaving a value the contract would never render.
    """
    chosen = (preset or "").strip()
    style = (custom_style or "").strip()
    if chosen not in (*VOICE_PRESETS, CUSTOM_VOICE):
        raise ValueError("Pick one of the voices offered.")
    if chosen != CUSTOM_VOICE:
        return {"customer_voice_preset": chosen, "customer_voice_custom_style": ""}
    if not style:
        raise ValueError("Describe how you want your assistant to sound.")
    if len(style) > CUSTOM_VOICE_MAX:
        raise ValueError(f"Keep the description to {CUSTOM_VOICE_MAX} characters or fewer.")
    return {"customer_voice_preset": CUSTOM_VOICE, "customer_voice_custom_style": style}


def _normalize_abn(value: str) -> str:
    """Stored as the eleven digits, the way the interview stores them.

    Cleared means "no ABN" - the same stated answer the interview's "No, not
    yet" chip leaves - rather than "never asked", which is what an empty string
    means everywhere else in the draft.
    """
    if not value.strip() or value.strip().lower() == NO_ABN:
        return NO_ABN
    digits = "".join(char for char in value if char.isdigit())
    if len(digits) != 11:
        raise ValueError("An ABN is 11 digits.")
    return digits


@router.get("/profile", response_model=BusinessProfile)
async def get_profile(
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_owner)],
) -> dict[str, str]:
    return await service.read_profile(tenant_id=admin.tenant_id)


@router.patch("/profile", response_model=BusinessProfile)
async def patch_profile(
    body: ProfileUpdate,
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_owner)],
) -> dict[str, str]:
    try:
        fields = body.normalized()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    if not fields:
        return await service.read_profile(tenant_id=admin.tenant_id)
    return await service.write_profile(tenant_id=admin.tenant_id, fields=fields)


@router.put("/cover", status_code=status.HTTP_204_NO_CONTENT)
async def put_cover(
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_owner)],
    file: Annotated[UploadFile, File()],
) -> Response:
    mime, data = await _image_upload(file)
    try:
        await service.write_cover(
            tenant_id=admin.tenant_id, mime=mime, data=data, cloudinary=Cloudinary()
        )
    except MediaUploadError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _image_upload(file: UploadFile) -> tuple[str, bytes]:
    data = await file.read()
    mime = (file.content_type or "").split(";")[0].strip().lower()
    if mime not in ALLOWED_COVER_MIME:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="the image must be a JPEG, PNG or WebP image",
        )
    if len(data) > MAX_COVER_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"the image must be under {MAX_COVER_BYTES // (1024 * 1024)}MB",
        )
    if not data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="the file is empty"
        )
    return mime, data


@router.get("/cover")
async def get_cover(
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_owner)],
) -> Response:
    cloud_url = await service.read_cover_url(tenant_id=admin.tenant_id, role=service.COVER_KIND)
    if cloud_url:
        return RedirectResponse(cloud_url)
    found = await service.read_cover(tenant_id=admin.tenant_id)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no cover photo")
    mime, data, updated_at = found
    return Response(
        content=data,
        media_type=mime,
        headers={
            # Private: this is one tenant's own image behind their own session.
            # The mtime ETag is what stops the browser refetching it on every
            # visit to the page while still showing a new one immediately.
            "Cache-Control": "private, max-age=0, must-revalidate",
            "ETag": f'"{updated_at.timestamp()}"',
        },
    )


@router.delete("/cover", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cover(
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_owner)],
) -> Response:
    try:
        await service.delete_cover(tenant_id=admin.tenant_id)
    except MediaUploadError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class OfferingMediaUrl(BaseModel):
    url: str = Field(min_length=8, max_length=2000)

    @field_validator("url")
    @classmethod
    def _url(cls, value: str) -> str:
        parsed = urlparse(value.strip())
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("media URL must be an absolute http:// or https:// URL")
        return value.strip()


@router.put("/offerings/{offering_id}/media/upload", response_model=OfferingMedia)
async def upload_offering_media(
    offering_id: UUID,
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_owner)],
    file: Annotated[UploadFile, File()],
) -> OfferingMedia:
    data = await file.read()
    if not data or len(data) > 20 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="media must be under 20MB"
        )
    mime = (file.content_type or "").split(";")[0].strip().lower()
    if not (mime.startswith("image/") or mime.startswith("video/")):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="upload an image or video"
        )
    try:
        return OfferingMedia(
            **await service.set_offering_media(
                tenant_id=admin.tenant_id, offering_id=offering_id, value=data, mime=mime
            )
        )
    except MediaUploadError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="offering not found"
        ) from exc


@router.put("/offerings/{offering_id}/media/url", response_model=OfferingMedia)
async def set_offering_media_url(
    offering_id: UUID,
    body: OfferingMediaUrl,
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_owner)],
) -> OfferingMedia:
    try:
        return OfferingMedia(
            **await service.set_offering_media(
                tenant_id=admin.tenant_id, offering_id=offering_id, value=body.url
            )
        )
    except MediaUploadError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="offering not found"
        ) from exc


@router.delete("/offerings/{offering_id}/media", status_code=status.HTTP_204_NO_CONTENT)
async def remove_offering_media(
    offering_id: UUID,
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_owner)],
) -> Response:
    cloudinary = Cloudinary()
    try:
        removed = await service.delete_media(
            tenant_id=admin.tenant_id,
            offering_id=offering_id,
            role="offering",
            cloudinary=cloudinary,
        )
    except MediaUploadError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="media not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
