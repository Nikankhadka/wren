"""T-006 / T-042: tenant-admin onboarding (Surface-2 Copilot).

The T-006 state machine is retired; turn logic lives in app/onboarding/agent.py.
JSON contract on POST /api/onboarding/message unchanged.
POST /api/onboarding/message/stream returns SSE in this event order:
``progress`` -> ``token``* -> [``redraft``] -> ``token``* -> ``reply`` ->
``state`` -> ``done``. ``token`` deltas reassemble into the reply; ``redraft``
signals the price-echo guard tripped and the client should drop tokens so far.
Handlers live in controller.py, persistence in service.py.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator, model_validator

from app.features.knowledge.api import KnowledgeRecord
from app.features.knowledge.models import KnowledgeSection
from app.features.onboarding import controller
from app.features.tenants.slug import validate_slug
from app.llm.dependency import get_embedder_dependency, get_llm_provider
from app.llm.embedder import Embedder
from app.llm.provider import LLMProvider
from app.onboarding.beats import InputSpec
from app.onboarding.flow import PendingOffering
from app.shared import auth
from app.shared.errors import request_id
from app.shared.limits import LimitTimeout

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


class OnboardingStateResponse(BaseModel):
    stage: str
    prompt: str
    # O-1: the draft is a flat profile - one string per captured field.
    draft: dict[str, str]
    completed: bool
    history: list[dict[str, str]]
    input: InputSpec | None
    can_confirm: bool
    suggested_slug: str | None
    offering_candidates: list[PendingOffering]
    paused_beat: str | None


class SelectionPayload(BaseModel):
    beat: str
    values: list[str] = Field(default_factory=list)


class OnboardingMessageRequest(BaseModel):
    text: str | None = None
    selection: SelectionPayload | None = None
    resume: bool = False

    @model_validator(mode="after")
    def _exactly_one_of_text_or_selection(self) -> OnboardingMessageRequest:
        if sum((self.text is not None, self.selection is not None, self.resume)) != 1:
            raise ValueError("provide exactly one of 'text', 'selection', or 'resume'")
        return self


class OnboardingConfirmResponse(BaseModel):
    tenant_id: UUID
    slug: str


class OnboardingConfirmRequest(BaseModel):
    # W-7: the go-live screen confirms the public address only. Name and type
    # were captured (and validated) during the interview; the founder asked not
    # to re-confirm details already given, so this carries just the slug.
    slug: str | None = Field(default=None, min_length=3, max_length=40)

    @field_validator("slug")
    @classmethod
    def _check_slug(cls, value: str | None) -> str | None:
        return value if value is None else validate_slug(value)


class OnboardingKnowledgeRequest(BaseModel):
    sections: list[KnowledgeSection] = Field(default_factory=list)
    offerings: list[PendingOffering] = Field(default_factory=list)


class OnboardingKnowledgeResponse(BaseModel):
    record: KnowledgeRecord
    offering_candidates: list[PendingOffering]


class OnboardingKnowledgeBatchDocument(BaseModel):
    document_id: UUID
    sections: list[KnowledgeSection] = Field(default_factory=list)


class OnboardingKnowledgeBatchRequest(BaseModel):
    documents: list[OnboardingKnowledgeBatchDocument] = Field(min_length=1, max_length=5)
    offerings: list[PendingOffering] = Field(default_factory=list)
    accept_price_changes: bool = False

    @field_validator("documents")
    @classmethod
    def _document_ids_are_unique(
        cls, documents: list[OnboardingKnowledgeBatchDocument]
    ) -> list[OnboardingKnowledgeBatchDocument]:
        if len({document.document_id for document in documents}) != len(documents):
            raise ValueError("document_id values must be unique")
        return documents


class OnboardingKnowledgeBatchFailure(BaseModel):
    document_id: UUID
    error: str


class OnboardingKnowledgeBatchResponse(BaseModel):
    published: list[UUID]
    failed: list[OnboardingKnowledgeBatchFailure]
    offering_candidates: list[PendingOffering]


@router.get("/state", response_model=OnboardingStateResponse)
async def get_state(
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_owner)],
) -> OnboardingStateResponse:
    record = await controller.load_record_state(tenant_id=admin.tenant_id)
    return OnboardingStateResponse(**record)


# W-11a: registered before the "/knowledge/{document_id}" route below - Starlette
# matches routes in declaration order and "{document_id}" would otherwise
# swallow "/knowledge/batch" (matching "batch" as the path segment, then 422ing
# when FastAPI tries to parse it as a UUID) before this route is ever tried.
@router.put("/knowledge/batch", response_model=OnboardingKnowledgeBatchResponse)
async def save_onboarding_knowledge_batch(
    body: OnboardingKnowledgeBatchRequest,
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_owner)],
    embedder: Annotated[Embedder, Depends(get_embedder_dependency)],
) -> OnboardingKnowledgeBatchResponse:
    published, failed, offerings = await controller.save_onboarding_knowledge_batch(
        tenant_id=admin.tenant_id,
        documents=[
            (document.document_id, [section.model_dump() for section in document.sections])
            for document in body.documents
        ],
        offerings=body.offerings,
        accept_price_changes=body.accept_price_changes,
        embedder=embedder,
    )
    return OnboardingKnowledgeBatchResponse(
        published=published,
        failed=[
            OnboardingKnowledgeBatchFailure(document_id=document_id, error=error)
            for document_id, error in failed
        ],
        offering_candidates=offerings,
    )


@router.put("/knowledge/{document_id}", response_model=OnboardingKnowledgeResponse)
async def save_onboarding_knowledge(
    document_id: UUID,
    body: OnboardingKnowledgeRequest,
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_owner)],
    embedder: Annotated[Embedder, Depends(get_embedder_dependency)],
) -> OnboardingKnowledgeResponse:
    record, offerings = await controller.save_onboarding_knowledge(
        tenant_id=admin.tenant_id,
        document_id=document_id,
        sections=[section.model_dump() for section in body.sections],
        offerings=body.offerings,
        embedder=embedder,
    )
    return OnboardingKnowledgeResponse(
        record=KnowledgeRecord(**record), offering_candidates=offerings
    )


@router.post("/message", response_model=OnboardingStateResponse)
async def post_message(
    body: OnboardingMessageRequest,
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_owner)],
    provider: Annotated[LLMProvider, Depends(get_llm_provider)],
    embedder: Annotated[Embedder, Depends(get_embedder_dependency)],
) -> OnboardingStateResponse:
    if body.resume:
        record_data = await controller.run_resume(tenant_id=admin.tenant_id)
        return OnboardingStateResponse(**controller.response_from_record(record_data))
    if body.selection is not None:
        record_data = await controller.run_selection(
            tenant_id=admin.tenant_id,
            beat_key=body.selection.beat,
            values=body.selection.values,
        )
        return OnboardingStateResponse(**controller.response_from_record(record_data))
    assert body.text is not None
    record_data = await controller.run_message(
        tenant_id=admin.tenant_id, text=body.text, provider=provider, embedder=embedder
    )
    return OnboardingStateResponse(**controller.response_from_record(record_data))


@router.post("/message/stream")
async def post_message_stream(
    request: Request,
    body: OnboardingMessageRequest,
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_owner)],
    provider: Annotated[LLMProvider, Depends(get_llm_provider)],
    embedder: Annotated[Embedder, Depends(get_embedder_dependency)],
) -> StreamingResponse:
    if body.text is None:
        raise HTTPException(status_code=400, detail="stream accepts text messages only")
    text = body.text

    async def _stream() -> AsyncIterator[str]:
        async def _sse(event: dict[str, object]) -> str:
            return f"data: {json.dumps(event)}\n\n"

        stream_started = time.perf_counter()
        try:
            async for event in controller.run_message_stream(
                tenant_id=admin.tenant_id, text=text, provider=provider, embedder=embedder
            ):
                yield await _sse(event)
        except HTTPException as exc:
            yield await _sse(
                {
                    "type": "error",
                    "code": f"http_{exc.status_code}",
                    "detail": "The request could not be completed.",
                    "request_id": request_id(request),
                }
            )
            return
        except LimitTimeout:
            yield await _sse(
                {
                    "type": "error",
                    "code": "timeout",
                    "detail": "That took too long - please send your message again.",
                    "request_id": request_id(request),
                }
            )
            return
        except Exception:
            # Never let an unexpected failure become a silent empty stream
            # (the client would hang on a forever-streaming bubble).
            logger.exception("onboarding stream failed")
            yield await _sse(
                {
                    "type": "error",
                    "code": "internal_error",
                    "detail": "Something went wrong on my side - please send that again.",
                    "request_id": request_id(request),
                }
            )
            return
        logger.info(
            "onboarding stream",
            extra={
                "step": "stream_done",
                "duration_ms": round((time.perf_counter() - stream_started) * 1000, 1),
            },
        )

    return StreamingResponse(_stream(), media_type="text/event-stream")


@router.post("/confirm", response_model=OnboardingConfirmResponse)
async def confirm(
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_owner)],
    body: OnboardingConfirmRequest | None = None,
    embedder: Annotated[Embedder | None, Depends(get_embedder_dependency)] = None,
) -> OnboardingConfirmResponse:
    result = await controller.confirm(
        tenant_id=admin.tenant_id,
        slug=body.slug if body else None,
        embedder=embedder,
    )
    return OnboardingConfirmResponse(**result)
