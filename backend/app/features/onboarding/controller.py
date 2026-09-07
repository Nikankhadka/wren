"""Onboarding orchestration: turn loop, selections, and confirm gating.

Moved out of api/onboarding.py. Holds the business order of a confirm (gate,
then persist) and the state-shaped response builder. The LLM turn loop runs in
app/onboarding/agent.py. O-12 keeps fixed values on a deterministic server path
so extraction cannot desynchronise a beat.
"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, status

from app.features.business.offering_candidates import normalize_name
from app.features.knowledge import service as knowledge_service
from app.features.onboarding import service
from app.features.tenants.slug import suggested_slug, validate_slug
from app.llm.embedder import Embedder
from app.llm.provider import LLMProvider
from app.onboarding import beats
from app.onboarding.agent import (
    OnboardingRecord,
    confirm_pending_name,
    prepare_turn,
    prepare_url_turn,
    progress,
    resume_paused_beat,
    run_turn,
    selection_reply,
    stream_reply,
)
from app.onboarding.flow import (
    PendingOffering,
    ProfileDraft,
    customer_voice_for,
    merge_offerings,
    system_prompt_for,
)
from app.onboarding.tools import request_finalize
from app.shared.limits import DEFAULT_LLM_TIMEOUT_S, TimeLimitedProvider

logger = logging.getLogger("app.onboarding.controller")

# O-7: three shapes of link, in the order an owner is likely to paste one. A
# bare host only counts when a path follows it or it starts with "www.", and
# its last label must be alphabetic - that is what keeps "$16.50 a plate" and
# "16.50/plate" out while letting "ubereats.com/store/x" in. Before O-7 only
# the first branch matched, so a pasted bare domain was never even attempted.
_URL_RE = re.compile(
    r"""
    (?:
        https?://[^\s"'<>]+                                  # an explicit URL
      | www\.[^\s"'<>]+                                      # a www host, scheme omitted
      | (?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}       # host, alphabetic TLD
        /[^\s"'<>]*                                          # ... only with a path
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

# O-3: knowledge is never a blocking beat. A page we cannot read offers the two
# other ways in and then lets the interview move on - the owner can fill this in
# whenever, from the Knowledge screen.
#
# O-7: the line now names the situation instead of implying the owner mistyped
# something. Marketplace and social pages (Uber Eats, Instagram, Facebook) build
# themselves in the browser and turn readers away at the door, so the honest
# answer is that this page cannot be read, not that the link was wrong.
_URL_SCRAPE_FAILED = (
    "I couldn't read that page - some sites don't let anything but a browser in. "
    "Tell me in a sentence what you do, or send me a file instead. Either way you "
    "can add your services, pricing and the rest any time from Settings > Knowledge."
)


def _url_failure_code(exc: ValueError) -> str:
    """Map fetcher's deliberately safe diagnostics to stable log categories."""
    message = str(exc)
    if message.startswith("could not read this URL (HTTP"):
        return "upstream_http"
    for prefix, code in (
        ("URL resolves to a blocked", "blocked_address"),
        ("URL credentials", "credentials_rejected"),
        ("URL port", "port_rejected"),
        ("unsupported URL", "scheme_rejected"),
        ("redirect", "redirect_rejected"),
        ("too many redirects", "redirect_limit"),
        ("URL did not return HTML", "media_type_rejected"),
        ("page body exceeds", "body_limit"),
        ("network peer", "peer_mismatch"),
    ):
        if message.startswith(prefix):
            return code
    return "fetch_failed"


def _find_url(text: str) -> str | None:
    """The first link in the message, trailing punctuation stripped, or None.

    A match without a scheme is returned with ``https://`` prepended, because
    that is what the owner meant and what ``fetch_page`` will accept.
    """
    match = _URL_RE.search(text)
    if match is None:
        return None
    url = match.group(0).rstrip(".,;:!?)")
    if not url.lower().startswith(("http://", "https://")):
        url = f"https://{url}"
    return url


def _state_event(record: OnboardingRecord) -> dict[str, object]:
    record_data = record.to_jsonb()
    stage, input_, can_confirm = progress(record)
    return {
        "type": "state",
        "stage": stage,
        "draft": record_data.get("draft", {}),
        "completed": record_data.get("completed", False),
        "input": input_.model_dump() if input_ else None,
        "can_confirm": can_confirm,
        # W-7: null until a business name exists, matching response_from_record.
        # suggested_slug("") is the reserved-name fallback "business-page", and
        # emitting it on early turns let the client lock it before the real name
        # was captured, so the go-live address showed "business-page" not the
        # business's own slug.
        "suggested_slug": suggested_slug(business_name)
        if (business_name := str(record_data.get("draft", {}).get("business_name", "")))
        else None,
        "offering_candidates": record_data.get("offering_candidates", []),
        "paused_beat": record.paused_beat,
    }


async def _scrape_and_draft(
    *, tenant_id: UUID, url: str, provider: LLMProvider
) -> tuple[str, str, dict[str, Any] | None]:
    """Fetch a URL once, then save the fetched source as an unread draft."""
    document_id = uuid4()
    page_text, title = await knowledge_service.scrape_url(url=url)
    record = await knowledge_service.draft_from_url_text(
        tenant_id=tenant_id,
        document_id=document_id,
        url=url,
        text=page_text,
        title=title,
        provider=provider,
    )
    return page_text, title, record


def response_from_record(record_data: dict[str, Any]) -> dict[str, Any]:
    onboarding = OnboardingRecord.from_jsonb(record_data)
    draft = onboarding.draft
    completed = onboarding.completed
    stage, input_, can_confirm = progress(onboarding)
    prompt = ""
    for msg in reversed(onboarding.history):
        if msg.get("role") == "assistant":
            prompt = msg.get("content", "")
            break
    if not prompt:
        # The opening ends with the first beat's own ask rather than a
        # paraphrase of it - same seam W-2 closes for every later question. W-9
        # fixes the wording; the composition is unchanged, so the question is
        # still written once, by the beat.
        prompt = (
            "Hi, I'm the Agencx setup assistant. I'll help set up your business. "
            f"{beats.BEAT_ORDER[0].ask}"
        )
    return {
        "stage": stage,
        "prompt": prompt,
        "draft": draft,
        "completed": completed,
        "history": onboarding.history,
        "input": input_.model_dump() if input_ else None,
        "can_confirm": can_confirm,
        # W-7: null until a business name exists. suggested_slug("") is the
        # reserved-name fallback "business-page" (truthy), so `or None` never
        # nulled it - the initial load then locked "business-page" into the
        # client's address field before the real name was ever captured.
        "suggested_slug": (
            suggested_slug(name) if (name := str(draft.get("business_name", ""))) else None
        ),
        "offering_candidates": onboarding.to_jsonb().get("offering_candidates", []),
        "paused_beat": onboarding.paused_beat,
    }


def _merge_document_candidates(record: OnboardingRecord, raw: Any) -> None:
    merged = {normalize_name(item.name): item for item in record.offering_candidates}
    for item in raw if isinstance(raw, list) else []:
        try:
            document = PendingOffering.model_validate(item)
        except (TypeError, ValueError):
            continue
        document = document.model_copy(update={"sources": ["document"]})
        key = normalize_name(document.name)
        existing = merged.get(key)
        # W-7: the document's price and description win an overlap.
        merged[key] = document if existing is None else merge_offerings(existing, document)
    record.offering_candidates = list(merged.values())


async def load_record_state(*, tenant_id: UUID) -> dict[str, Any]:
    record = await service.load_record(tenant_id=tenant_id)
    response = response_from_record(record)
    documents = await knowledge_service.list_records(tenant_id=tenant_id)
    if any(document["status"] == "draft" for document in documents):
        response["can_confirm"] = False
    return response


async def run_message(
    *, tenant_id: UUID, text: str, provider: LLMProvider, embedder: Embedder
) -> dict[str, Any]:
    record = await service.load_record(tenant_id=tenant_id)
    onboarding = OnboardingRecord.from_jsonb(record)
    if onboarding.completed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="onboarding already confirmed",
        )
    if onboarding.paused_beat:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="finish the paused field before sending another answer",
        )
    url = _find_url(text)
    if url is not None:
        return await _run_url_message(
            tenant_id=tenant_id,
            url=url,
            onboarding=onboarding,
            provider=provider,
            embedder=embedder,
        )
    # ponytail: use the platform default timeout rather than resolving the
    # tenant's per-tenant llm_timeout_s; resolve TenantLimits like
    # features/chat/controller.py if onboarding ever needs per-tenant overrides.
    bounded = TimeLimitedProvider(provider, DEFAULT_LLM_TIMEOUT_S)
    updated, _reply = await run_turn(admin_message=text, record=onboarding, provider=bounded)
    record_data = updated.to_jsonb()
    await service.save_record(tenant_id=tenant_id, record=record_data)
    return record_data


async def run_selection(*, tenant_id: UUID, beat_key: str, values: list[str]) -> dict[str, Any]:
    """Apply the current beat's fixed answer without an LLM call."""
    record = await service.load_record(tenant_id=tenant_id)
    onboarding = OnboardingRecord.from_jsonb(record)
    if onboarding.completed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="onboarding already confirmed",
        )
    if onboarding.paused_beat:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="finish the paused field before selecting an answer",
        )
    current = beats.next_beat(onboarding.draft, onboarding.skipped, onboarding.deferred)
    # A name waiting to be confirmed holds the interview on its own beat, which
    # is not always the one `next_beat` would ask next - a correction can leave
    # an earlier beat still open. `progress` emits the same key to the client.
    stage = (
        onboarding.pending_name["target"]
        if onboarding.pending_name
        else (current.key if current is not None else "confirm")
    )
    if stage != beat_key:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"stale selection - current beat is {stage}",
        )
    # W-9 US-1: while a name waits on the owner's yes, the beat's own chips are
    # replaced by the confirmation chip, so this is the one selection
    # `apply_selection` does not own - it cannot see the proposal, and the
    # import direction (beats knows nothing of the record) is deliberate.
    pending = onboarding.pending_name
    if pending is not None and beat_key == pending["target"]:
        if values != ["yes"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="select one valid answer"
            )
        user_message = "Yes"
        ack = f"Saved as {confirm_pending_name(onboarding)}."
    else:
        try:
            user_message = beats.apply_selection(onboarding.draft, beat_key, values)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        ack = "Got it."
    reply = selection_reply(onboarding, ack)
    onboarding.history.append({"role": "user", "content": user_message})
    onboarding.history.append({"role": "assistant", "content": reply})
    record_data = onboarding.to_jsonb()
    await service.save_record(tenant_id=tenant_id, record=record_data)
    return record_data


async def run_resume(*, tenant_id: UUID) -> dict[str, Any]:
    """Resume a required field paused after both interview passes."""
    record = await service.load_record(tenant_id=tenant_id)
    onboarding = OnboardingRecord.from_jsonb(record)
    if onboarding.completed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="onboarding already confirmed"
        )
    try:
        reply = resume_paused_beat(onboarding)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    onboarding.history.append({"role": "assistant", "content": reply})
    record_data = onboarding.to_jsonb()
    await service.save_record(tenant_id=tenant_id, record=record_data)
    return record_data


async def _run_url_message(
    *,
    tenant_id: UUID,
    url: str,
    onboarding: OnboardingRecord,
    provider: LLMProvider,
    embedder: Embedder,
) -> dict[str, Any]:
    """Non-streamed URL turn: scrape + ingest, extract, return the read-back
    state. A failed scrape degrades to a calm ask-to-describe."""
    bounded = TimeLimitedProvider(provider, DEFAULT_LLM_TIMEOUT_S)
    try:
        page_text, _title, document = await _scrape_and_draft(
            tenant_id=tenant_id, url=url, provider=bounded
        )
    except ValueError as exc:
        # O-7: the owner gets one calm line either way, but the reason is not
        # thrown away. A 403, a page that renders itself in the browser, and a
        # dead host all read the same on screen and must not read the same here.
        logger.info("url scrape failed reason=%s", _url_failure_code(exc))
        onboarding.history.append({"role": "user", "content": url})
        onboarding.history.append({"role": "assistant", "content": _URL_SCRAPE_FAILED})
        await service.save_record(tenant_id=tenant_id, record=onboarding.to_jsonb())
        return onboarding.to_jsonb()

    if document:
        _merge_document_candidates(onboarding, document.get("offering_candidates", []))
    plan = await prepare_url_turn(url=url, page_text=page_text, record=onboarding, provider=bounded)
    plan.record.history.append({"role": "assistant", "content": plan.summary or ""})
    await service.save_record(tenant_id=tenant_id, record=plan.record.to_jsonb())
    return plan.record.to_jsonb()


async def run_message_stream(
    *, tenant_id: UUID, text: str, provider: LLMProvider, embedder: Embedder
) -> AsyncIterator[dict[str, object]]:
    """Streams one text turn as SSE-shaped events.

    Event order: ``progress`` -> ``token``* -> [``redraft``] -> ``token``* ->
    ``reply`` -> ``state`` -> ``done``. Two short DB writes per turn: the draft
    plus the user message persist before the stream starts (so a refresh
    mid-conversation survives), the assistant reply persists after the stream.
    A URL in the message routes to the site-as-shortcut turn (O-3).
    """
    record = await service.load_record(tenant_id=tenant_id)
    onboarding = OnboardingRecord.from_jsonb(record)
    if onboarding.completed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="onboarding already confirmed",
        )
    if onboarding.paused_beat:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="finish the paused field before sending another answer",
        )
    url = _find_url(text)
    if url is not None:
        async for event in _stream_url_turn(
            tenant_id=tenant_id,
            url=url,
            onboarding=onboarding,
            provider=provider,
            embedder=embedder,
        ):
            yield event
        return
    # ponytail: platform default timeout (see run_message above).
    bounded = TimeLimitedProvider(provider, DEFAULT_LLM_TIMEOUT_S)
    plan = await prepare_turn(admin_message=text, record=onboarding, provider=bounded)
    await service.save_record(tenant_id=tenant_id, record=plan.record.to_jsonb())

    yield {"type": "progress", "stage": "processing"}

    full = ""
    async for kind, payload in stream_reply(plan=plan, provider=bounded):
        if kind == "redraft":
            full = ""
            yield {"type": "redraft", "reason": payload}
        else:
            full += payload
            yield {"type": "token", "text": payload}
    # Kept for the old client; the new client reassembles ``token`` events.
    yield {"type": "reply", "text": full}

    plan.record.history.append({"role": "assistant", "content": full})
    await service.save_record(tenant_id=tenant_id, record=plan.record.to_jsonb())

    yield _state_event(plan.record)
    yield {"type": "done"}


async def _stream_url_turn(
    *,
    tenant_id: UUID,
    url: str,
    onboarding: OnboardingRecord,
    provider: LLMProvider,
    embedder: Embedder,
) -> AsyncIterator[dict[str, object]]:
    """Streams the site-as-shortcut turn (O-3): scrape + ingest, then extract
    the profile fields from the page and reply with a read-back for the owner
    to confirm or correct. A failed scrape degrades to a calm ask-to-describe,
    never a hang or an error chrome."""
    bounded = TimeLimitedProvider(provider, DEFAULT_LLM_TIMEOUT_S)
    # The stamp leads: it is what the owner reads while the fetch, the ingest and
    # the extract run, so it has to be on the wire before any of them start.
    yield {"type": "progress", "stage": "reading_site"}
    try:
        page_text, _title, document = await _scrape_and_draft(
            tenant_id=tenant_id, url=url, provider=bounded
        )
    except ValueError as exc:
        logger.info("url scrape failed reason=%s", _url_failure_code(exc))
        onboarding.history.append({"role": "user", "content": url})
        await service.save_record(tenant_id=tenant_id, record=onboarding.to_jsonb())
        yield {"type": "token", "text": _URL_SCRAPE_FAILED}
        yield {"type": "reply", "text": _URL_SCRAPE_FAILED}
        onboarding.history.append({"role": "assistant", "content": _URL_SCRAPE_FAILED})
        await service.save_record(tenant_id=tenant_id, record=onboarding.to_jsonb())
        yield _state_event(onboarding)
        yield {"type": "done"}
        return

    if document:
        _merge_document_candidates(onboarding, document.get("offering_candidates", []))
    plan = await prepare_url_turn(url=url, page_text=page_text, record=onboarding, provider=bounded)
    await service.save_record(tenant_id=tenant_id, record=plan.record.to_jsonb())

    full = ""
    async for kind, payload in stream_reply(plan=plan, provider=bounded):
        if kind == "redraft":
            full = ""
            yield {"type": "redraft", "reason": payload}
        else:
            full += payload
            yield {"type": "token", "text": payload}
    yield {"type": "reply", "text": full}

    plan.record.history.append({"role": "assistant", "content": full})
    await service.save_record(tenant_id=tenant_id, record=plan.record.to_jsonb())

    yield _state_event(plan.record)
    yield {"type": "done"}


async def save_onboarding_knowledge(
    *,
    tenant_id: UUID,
    document_id: UUID,
    sections: list[dict[str, str]],
    offerings: list[PendingOffering],
    embedder: Embedder,
) -> tuple[dict[str, Any], list[PendingOffering]]:
    """Publish one reviewed source and retain its catalog decisions in onboarding."""
    keys: set[str] = set()
    for offering in offerings:
        key = normalize_name(offering.name)
        if not key or key in keys:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="offering names must be unique",
            )
        keys.add(key)

    record = await knowledge_service.publish_record(
        tenant_id=tenant_id,
        document_id=document_id,
        sections=sections,
        offerings=[item.model_dump() for item in offerings],
        embedder=embedder,
    )
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")

    onboarding = OnboardingRecord.from_jsonb(await service.load_record(tenant_id=tenant_id))
    onboarding.offering_candidates = offerings
    await service.save_record(tenant_id=tenant_id, record=onboarding.to_jsonb())
    return record, offerings


async def confirm(
    *,
    tenant_id: UUID,
    slug: str | None = None,
    embedder: Embedder | None = None,
) -> dict[str, Any]:
    record = await service.load_record(tenant_id=tenant_id)
    onboarding = OnboardingRecord.from_jsonb(record)
    if onboarding.completed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="already confirmed",
        )
    if onboarding.paused_beat:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="finish the paused field before going live",
        )
    documents = await knowledge_service.list_records(tenant_id=tenant_id)
    if any(document["status"] == "draft" for document in documents):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="review or discard every knowledge draft before going live",
        )
    draft = onboarding.draft
    gate = request_finalize(draft, onboarding.skipped)
    if not gate.ok:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"incomplete - missing: {'; '.join(gate.missing)}",
        )
    # The gate above guarantees all seven fields; extra keys (a pre-O-1 draft's
    # orphan sections) are ignored rather than rejected.
    profile = ProfileDraft.model_validate(draft)
    public_slug = validate_slug(slug or suggested_slug(profile.business_name))
    system_prompt = system_prompt_for(profile.business_name, profile.business_type)
    onboarding.completed = True
    try:
        await service.apply_confirmation(
            tenant_id=tenant_id,
            system_prompt=system_prompt,
            business_name=profile.business_name,
            slug=public_slug,
            profile=profile.model_dump(),
            # W-9: the voice the owner picked, in the structured shape the
            # customer assistant reads. Expression only - it never carries a
            # fact, a price, or an escalation rule.
            customer_voice=customer_voice_for(profile),
            completed_record=onboarding.to_jsonb(),
            offering_candidates=onboarding.offering_candidates,
            embedder=embedder,
        )
    except service.PublicSlugTakenError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That page address is already taken. Choose another.",
        ) from exc
    return {"tenant_id": tenant_id, "slug": public_slug}
