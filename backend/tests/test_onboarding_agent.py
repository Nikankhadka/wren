"""O-1: lean onboarding turn-loop unit tests.

Tests the agent turn loop (structured extraction + one ``save_profile`` merge),
the completeness gate over the seven lean beats, off-topic handling, the price
echo check, and record migration to v3.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from typing import Any

import pytest

from app.features.business.service import profile_tagline
from app.llm.provider import ChatMessage, SchemaT
from app.onboarding import beats
from app.onboarding.agent import (
    _COPILOT,
    _EXTRACT_PROMPT,
    _KNOWLEDGE_OFFER,
    Directive,
    OnboardingRecord,
    _ack,
    _activation_summary,
    _echo,
    _usable,
    confirm_pending_name,
    prepare_turn,
    prepare_url_turn,
    progress,
    resume_paused_beat,
    run_turn,
    stream_reply,
)
from app.onboarding.flow import (
    PendingOffering,
    ProfileDraft,
    SourceReference,
    customer_voice_for,
)
from app.onboarding.tools import request_finalize, save_profile
from app.shared.voice import CUSTOM_VOICE_MAX
from tests.fakes import BaseFakeProvider

# --- fake providers ------------------------------------------------------------


class _ExtractFake(BaseFakeProvider):
    """Returns a sequence of DraftUpdate dicts, then a text-only chat reply.

    Records the extract() inputs and chat() messages so tests can assert what
    the agent loop feeds back to the model (stateful extraction context and the
    composed directive).
    """

    def __init__(
        self,
        updates: list[dict[str, Any]] | None = None,
        replies: list[str] | None = None,
    ):
        self._updates = list(updates or [])
        self._replies = replies or ["Got it."]
        self._update_idx = 0
        self._reply_idx = 0
        self.extract_inputs: list[str] = []
        self.chat_messages: list[list[ChatMessage]] = []
        self.stream_calls: list[list[ChatMessage]] = []

    async def extract(
        self, *, system_prompt: str, user_input: str, schema: type[SchemaT]
    ) -> SchemaT:
        self.extract_inputs.append(user_input)
        if self._update_idx < len(self._updates):
            data = self._updates[self._update_idx]
            self._update_idx += 1
            return schema.model_validate(data)
        return schema.model_validate({})

    async def chat(self, messages: list[ChatMessage]) -> str:
        self.chat_messages.append(messages)
        r = self._replies[self._reply_idx % len(self._replies)]
        self._reply_idx += 1
        return r

    async def chat_stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        self.stream_calls.append(messages)
        r = self._replies[self._reply_idx % len(self._replies)]
        self._reply_idx += 1
        mid = max(1, len(r) // 2)
        yield r[:mid]
        yield r[mid:]


# --- tool execution ------------------------------------------------------------


def test_save_profile_merges_only_non_empty_fields() -> None:
    draft: dict[str, Any] = {"owner_display_name": "Sam", "business_name": "Bytefix Repairs"}
    result = save_profile(draft, ProfileDraft(business_type="phone repair shop"))

    assert result["business_type"] == "phone repair shop"
    # An empty field must not blank out what an earlier turn captured.
    assert result["owner_display_name"] == "Sam"
    assert result["business_name"] == "Bytefix Repairs"


def test_save_profile_accumulates_across_turns() -> None:
    """US-1: the loop saves a partial profile per turn and merges them."""
    draft: dict[str, Any] = {}
    save_profile(draft, ProfileDraft(owner_display_name="Sam", business_name="Bytefix Repairs"))
    save_profile(draft, ProfileDraft(hours="Mon-Fri 9-6", contact="555-0100"))

    assert draft == {
        "owner_display_name": "Sam",
        "business_name": "Bytefix Repairs",
        "hours": "Mon-Fri 9-6",
        "contact": "555-0100",
    }


def test_save_profile_overwrites_a_corrected_field() -> None:
    draft: dict[str, Any] = {"business_name": "Bytefix"}
    save_profile(draft, ProfileDraft(business_name="Bytefix Repairs"))

    assert draft["business_name"] == "Bytefix Repairs"


def test_save_profile_only_accepts_an_abn_or_an_explicit_no() -> None:
    draft: dict[str, Any] = {}
    save_profile(draft, ProfileDraft(abn="yes"))
    assert "abn" not in draft

    save_profile(draft, ProfileDraft(abn="51 824 753 556"))
    assert draft["abn"] == "51824753556"

    save_profile(draft, ProfileDraft(abn=beats.NO_ABN))
    assert draft["abn"] == beats.NO_ABN


# --- completeness gate ---------------------------------------------------------


def _complete_draft() -> dict[str, Any]:
    return {
        "owner_display_name": "Sam",
        "business_name": "Bytefix Repairs",
        "business_type": "phone repair shop",
        "headcount": "just me",
        "hours": "Mon-Fri 9-6",
        "services": "screen repairs, battery replacements",
        "contact": "555-0100",
        "abn": "51 824 753 556",
        "gst": "yes",
        # W-9: the voice beat sits between `services` and `contact`, and it is
        # answered like any other beat before the interview is complete.
        "customer_voice_preset": "warm_casual",
    }


def test_gst_is_not_asked_of_a_business_without_an_abn() -> None:
    """O-6: the prototype's `handleAbn()` "no" branch goes straight past GST -
    a registration you cannot hold is not a question. Expressed in the beat's
    own predicate, so the gate and the interview cannot disagree about it."""
    without = _complete_draft() | {"abn": beats.NO_ABN, "gst": ""}
    assert beats.next_beat(without) is None
    assert request_finalize(without).ok

    # ...but a business that gave an ABN is still asked.
    with_abn = _complete_draft() | {"abn": "51 824 753 556", "gst": ""}
    nxt = beats.next_beat(with_abn)
    assert nxt is not None and nxt.key == "gst"
    assert "GST registration" in request_finalize(with_abn).missing


def test_no_beat_branches_on_the_business_type() -> None:
    """I8: the question set is the same for every vertical. ABN and GST are
    conditional on a previous *answer*, never on what the business does."""
    asked = []
    for business_type in ("dental clinic", "butcher", "online store"):
        draft = {"business_type": business_type}
        keys = []
        while (nxt := beats.next_beat(draft)) is not None:
            keys.append(nxt.key)
            draft[nxt.key] = "x"
        asked.append(keys)
    assert asked[0] == asked[1] == asked[2]


def test_completeness_gate_passes_when_every_field_present() -> None:
    result = request_finalize(_complete_draft())
    assert result.ok
    assert result.missing == []


def test_completeness_gate_fails_when_fields_missing() -> None:
    result = request_finalize({"owner_display_name": "Sam"})
    assert not result.ok
    assert any("business name" in m for m in result.missing)
    assert any("contact details" in m for m in result.missing)


@pytest.mark.parametrize(
    ("field", "label"),
    [
        ("owner_display_name", "your name"),
        ("business_name", "business name"),
        ("business_type", "business type"),
        ("headcount", "team size"),
        ("hours", "opening hours"),
        ("services", "what you offer"),
        ("contact", "contact details"),
    ],
)
def test_completeness_gate_enumerates_each_missing_field(field: str, label: str) -> None:
    """US-2: every lean field is required, and the gate names the one missing."""
    draft = _complete_draft()
    del draft[field]

    result = request_finalize(draft)

    assert not result.ok
    assert result.missing == [label]


def test_completeness_gate_is_the_same_for_every_business_type() -> None:
    """I8: the question set never branches on the vertical."""
    clinic = _complete_draft() | {"business_type": "dental clinic"}
    store = _complete_draft() | {"business_type": "online store"}
    del clinic["hours"]
    del store["hours"]

    assert request_finalize(clinic).missing == request_finalize(store).missing


# --- price echo check ----------------------------------------------------------


def test_reply_with_any_price_is_flagged() -> None:
    """The lean profile captures no prices, so any figure is model-authored (I1)."""
    assert _echo("Screen repair costs $89.50.", _complete_draft())
    assert _echo("It's $30.", _complete_draft())


def test_reply_with_no_prices_is_not_flagged() -> None:
    assert not _echo("We offer screen repair.", _complete_draft())


# --- record migration ----------------------------------------------------------


def test_from_jsonb_drops_a_pre_o1_nested_draft() -> None:
    """A v2 draft shares no key with the lean profile, so the interview restarts."""
    v2 = {"version": 2, "draft": {"identity": {"description": "old shop"}}, "completed": False}
    record = OnboardingRecord.from_jsonb(v2)

    assert record.version == 4
    assert record.draft == {}
    assert not record.completed


def test_from_jsonb_keeps_a_completed_legacy_tenant_live() -> None:
    """A tenant that already went live must never be re-interviewed."""
    v2 = {"version": 2, "draft": {"identity": {"description": "old shop"}}, "completed": True}
    record = OnboardingRecord.from_jsonb(v2)

    assert record.completed
    assert record.draft == {}


def test_from_jsonb_migrates_the_oldest_format() -> None:
    legacy = {"state": {"draft": {"identity": {"description": "old shop"}}}, "completed": False}
    record = OnboardingRecord.from_jsonb(legacy)

    assert record.version == 4
    assert record.draft == {}


def test_from_jsonb_reads_v3_format() -> None:
    v3 = {"version": 3, "draft": {"business_name": "Bytefix Repairs"}, "completed": True}
    record = OnboardingRecord.from_jsonb(v3)

    assert record.draft["business_name"] == "Bytefix Repairs"
    assert record.completed


def test_a_v3_record_upgrades_to_v4_carrying_every_beat_key() -> None:
    """W-9: the owner-name beat is renamed in all five places a beat key lives.

    A rename that touched only the draft would strand an interview whose cursor,
    skip list, deferral list, or pause still said ``name``.
    """
    v3 = {
        "version": 3,
        "draft": {"name": "Sam", "business_name": "Bytefix Repairs"},
        "history": [{"role": "user", "content": "I'm Sam"}],
        "skipped": ["name"],
        "deferred": ["name"],
        "ask_beat": "name",
        "ask_count": 2,
        "paused_beat": "name",
        "knowledge_pending": True,
        "completed": True,
    }
    record = OnboardingRecord.from_jsonb(v3)

    assert record.version == 4
    assert record.draft == {"owner_display_name": "Sam", "business_name": "Bytefix Repairs"}
    assert record.skipped == ["owner_display_name"]
    assert record.deferred == ["owner_display_name"]
    assert record.ask_beat == "owner_display_name"
    assert record.paused_beat == "owner_display_name"
    # Everything else is carried forward untouched - progress, transcript, state.
    assert record.history == [{"role": "user", "content": "I'm Sam"}]
    assert (record.ask_count, record.knowledge_pending, record.completed) == (2, True, True)


def test_a_v3_record_without_the_renamed_beat_is_untouched() -> None:
    v3 = {"version": 3, "draft": {"business_name": "Bytefix Repairs"}, "ask_beat": "hours"}
    record = OnboardingRecord.from_jsonb(v3)

    assert record.draft == {"business_name": "Bytefix Repairs"}
    assert record.ask_beat == "hours"


def test_the_go_live_line_never_substitutes_the_owners_name() -> None:
    """W-9 US-2: the owner's private name is never the public business identity.

    Latent rather than user-visible: this line renders only once every beat is
    satisfied, and `business_name` is required, so the removed fallback was
    unreachable from the interview. It is gone all the same.
    """
    assert "Sam" not in _activation_summary({"owner_display_name": "Sam"})
    assert "Bytefix Repairs" in _activation_summary({"business_name": "Bytefix Repairs"})


def test_to_jsonb_roundtrips() -> None:
    record = OnboardingRecord(draft={"business_name": "Bytefix Repairs"}, completed=False)
    restored = OnboardingRecord.from_jsonb(record.to_jsonb())

    assert restored.draft == record.draft
    assert restored.completed == record.completed


def test_resume_replays_persisted_history() -> None:
    """US-4: a returning owner picks up from the persisted thread, nothing re-asked."""
    record = OnboardingRecord(
        draft={"owner_display_name": "Sam", "business_name": "Bytefix Repairs"},
        history=[
            {"role": "user", "content": "I'm Sam, we're Bytefix Repairs"},
            {"role": "assistant", "content": "Got it. What kind of business is it?"},
        ],
    )
    restored = OnboardingRecord.from_jsonb(record.to_jsonb())

    assert restored.history == record.history
    assert restored.draft["business_name"] == "Bytefix Repairs"


# --- agent turn loop -----------------------------------------------------------


@pytest.mark.asyncio
async def test_run_turn_extracts_from_a_complex_message() -> None:
    """A free-form answer must be captured on the first try, not dropped
    because the model replied in prose."""
    provider = _ExtractFake(
        updates=[
            {
                "profile": {
                    "business_type": "mobile phone business",
                    "services": "phone cases and accessories",
                }
            },
        ],
        replies=["Got it - a mobile phone business! What are your opening hours?"],
    )
    record = OnboardingRecord()
    updated, reply = await run_turn(
        admin_message=(
            "this is a mobile phone business mostly selling phone cases and everything else"
        ),
        record=record,
        provider=provider,
    )

    assert updated.draft["business_type"] == "mobile phone business"
    assert updated.draft["services"] == "phone cases and accessories"
    assert "mobile phone" in reply
    assert len(updated.history) >= 2


@pytest.mark.asyncio
async def test_run_turn_proposes_a_business_name_before_it_persists_one() -> None:
    """W-9 US-1: a name is shown back and confirmed, never written on sight."""
    provider = _ExtractFake(
        updates=[{"profile": {"business_name": "Bytefix Repairs"}}],
        replies=["Got it - Bytefix Repairs!"],
    )
    record = OnboardingRecord(draft={"owner_display_name": "Sam"})
    updated, reply = await run_turn(
        admin_message="we are called Bytefix Repairs", record=record, provider=provider
    )

    assert "business_name" not in updated.draft
    assert updated.pending_name == {
        "target": "business_name",
        "raw": "we are called Bytefix Repairs",
        "proposal": "Bytefix Repairs",
    }
    # The proposal is the server's own words, so the model cannot embellish it.
    assert reply == 'I have "Bytefix Repairs". Is that right?'
    assert provider.chat_messages == []


@pytest.mark.asyncio
async def test_run_turn_acknowledges_every_field_it_captured() -> None:
    provider = _ExtractFake(
        updates=[{"profile": {"hours": "Mon-Fri 9-6", "contact": "555-0100"}}],
        replies=["Noted."],
    )
    record = OnboardingRecord(draft={"owner_display_name": "Sam"})
    _updated, _reply = await run_turn(
        admin_message="we're open Mon-Fri 9-6, call 555-0100", record=record, provider=provider
    )

    system_prompts = [m["content"] for m in provider.chat_messages[0] if m["role"] == "system"]
    assert any("opening hours" in p and "contact details" in p for p in system_prompts)


@pytest.mark.asyncio
async def test_run_turn_uses_the_authoritative_next_beat() -> None:
    """W-2 US-1: the model writes the acknowledgment, the server writes the question."""
    provider = _ExtractFake(updates=[{}], replies=["Sure thing."])
    record = OnboardingRecord(draft={"owner_display_name": "Sam"})
    _updated, reply = await run_turn(admin_message="ok go on", record=record, provider=provider)

    assert reply == "Sure thing. What does the business go by?"
    # The question is appended by the server, so it is never in the model's brief.
    system_prompts = [m["content"] for m in provider.chat_messages[0] if m["role"] == "system"]
    assert not any("What does the business go by?" in p for p in system_prompts)
    assert any("Do not ask a question" in p for p in system_prompts)


@pytest.mark.asyncio
async def test_run_turn_extraction_is_stateful() -> None:
    """The extract call sees the already-captured draft so it can fill what is
    still missing instead of re-asking for what it has."""
    provider = _ExtractFake(updates=[{"profile": {"headcount": "just me"}}], replies=["Noted."])
    record = OnboardingRecord(draft={"business_name": "Bytefix Repairs"})
    _updated, _reply = await run_turn(
        admin_message="it's just me", record=record, provider=provider
    )

    assert "Bytefix Repairs" in provider.extract_inputs[0]


@pytest.mark.asyncio
async def test_run_turn_handles_completed_record() -> None:
    provider = _ExtractFake(updates=[], replies=[])
    record = OnboardingRecord(completed=True)
    updated, reply = await run_turn(admin_message="anything", record=record, provider=provider)
    assert "already complete" in reply
    assert updated.completed


@pytest.mark.asyncio
async def test_run_turn_off_topic_answers_gently() -> None:
    """US-3: one-line answer plus a redirect, and no firmness escalation."""
    provider = _ExtractFake(
        updates=[
            {
                "off_topic": True,
                "meta_reply": "I'm here to help you set up your business.",
            },
        ],
        replies=["I'm here to help you set up your business. What is your business called?"],
    )
    record = OnboardingRecord(draft={"owner_display_name": "Sam"})
    updated, reply = await run_turn(admin_message="who are you", record=record, provider=provider)

    # W-2: an off-topic turn is persisted like any other, so the stored record
    # and the emitted state cannot drift apart and rewind the beat pointer.
    assert updated.off_topic_count == 1
    assert [entry["role"] for entry in updated.history] == ["user", "assistant"]
    assert "set up your business" in reply
    system_prompts = [m["content"] for m in provider.chat_messages[0] if m["role"] == "system"]
    assert any("Briefly answer" in p for p in system_prompts)


@pytest.mark.asyncio
async def test_off_topic_turn_does_not_burn_one_of_a_beats_two_asks() -> None:
    """W-2 US-4: noise is not a failed answer, so it costs the owner nothing."""
    provider = _ExtractFake(
        updates=[
            {
                "off_topic": True,
                "meta_reply": "I'm here to help.",
            }
        ],
        replies=["I'm here to help. What is your business called?"],
    )
    record = OnboardingRecord(
        draft={"owner_display_name": "Sam"},
        history=[
            {"role": "user", "content": "I'm Sam"},
            {"role": "assistant", "content": "Got it."},
        ],
    )
    record.ask_beat, record.ask_count = "business_name", 1
    updated, _reply = await run_turn(admin_message="hi", record=record, provider=provider)

    assert updated.ask_count == 1
    assert updated.ask_beat == "business_name"
    assert updated.draft["owner_display_name"] == "Sam"
    # The turn is still recorded - only the ask counter is left alone.
    assert len(updated.history) == 4


@pytest.mark.asyncio
async def test_run_turn_price_echo_triggers_redraft() -> None:
    """When the model authors a price, the reply is redrafted without it."""
    provider = _ExtractFake(
        updates=[{"profile": {"business_type": "phone repair shop"}}],
        replies=[
            "Screen repair is $199.",  # model-authored price - triggers redraft
            "Got it, I've captured what you do.",
        ],
    )
    record = OnboardingRecord(
        draft={"owner_display_name": "Sam", "business_name": "Bytefix Repairs"},
        ask_beat="business_type",
        ask_count=1,
    )
    updated, reply = await run_turn(admin_message="we fix phones", record=record, provider=provider)

    assert updated.draft["business_type"] == "phone repair shop"
    assert "$199" not in reply


# --- streaming split (prepare_turn / stream_reply) -----------------------------


@pytest.mark.asyncio
async def test_prepare_turn_sets_summary_once_the_profile_is_complete() -> None:
    provider = _ExtractFake(updates=[{"profile": {"contact": "555-0100"}}], replies=[])
    draft = _complete_draft()
    del draft["contact"]
    record = OnboardingRecord(draft=draft)

    plan = await prepare_turn(admin_message="call us on 555-0100", record=record, provider=provider)

    assert plan.summary is not None
    assert "Bytefix Repairs" in plan.summary
    assert "ready to go live" in plan.summary
    assert plan.reply_msgs is None
    # The user message is already on the record; the assistant reply is not.
    assert plan.record.history[-1]["role"] == "user"


@pytest.mark.asyncio
async def test_stream_reply_yields_summary_without_llm() -> None:
    provider = _ExtractFake(updates=[{"profile": {"contact": "555-0100"}}], replies=[])
    draft = _complete_draft()
    del draft["contact"]
    record = OnboardingRecord(draft=draft)
    plan = await prepare_turn(admin_message="call us on 555-0100", record=record, provider=provider)

    events = [event async for event in stream_reply(plan=plan, provider=provider)]

    assert plan.summary is not None
    assert events == [("token", plan.summary)]
    assert provider.stream_calls == []


@pytest.mark.asyncio
async def test_stream_reply_price_echo_redrafts() -> None:
    provider = _ExtractFake(
        updates=[{"profile": {"business_type": "phone repair shop"}}],
        replies=[
            "Screen repair is $199.",  # model-authored price - triggers redraft
            "Got it, I've captured what you do.",
        ],
    )
    record = OnboardingRecord()
    plan = await prepare_turn(admin_message="we fix phones", record=record, provider=provider)

    events = [event async for event in stream_reply(plan=plan, provider=provider)]
    kinds = [kind for kind, _ in events]
    assert "redraft" in kinds
    redraft_idx = kinds.index("redraft")
    assert events[redraft_idx] == ("redraft", "price_echo")

    before = "".join(payload for kind, payload in events[:redraft_idx] if kind == "token")
    assert "$199" in before
    after = "".join(payload for kind, payload in events[redraft_idx + 1 :] if kind == "token")
    assert "captured" in after
    assert len(provider.stream_calls) == 2


@pytest.mark.asyncio
async def test_the_owner_message_reaches_the_model_exactly_once() -> None:
    """W-9 US-5: the reply context carried the owner's message twice, every turn.

    ``prepare_turn`` appends it to history, the history slice therefore already
    carries it, and a second append put it in again. Both reply paths read the
    same list, so both are asserted here - and the fix is the message assembly,
    not a similarity check over the text (US-5 forbids that).
    """
    message = "middle eastern cafe"
    record = OnboardingRecord(
        draft={"owner_display_name": "Nikan", "business_name": "Sababa"},
        history=[
            {"role": "user", "content": "Sababa"},
            {"role": "assistant", "content": "Noted. In a few words, what kind of business is it?"},
        ],
        ask_beat="business_type",
        ask_count=1,
    )
    provider = _ExtractFake(
        updates=[{"profile": {"business_type": message}, "answered_asked": True}],
        replies=["Noted."],
    )
    plan = await prepare_turn(admin_message=message, record=record, provider=provider)

    assert plan.reply_msgs is not None
    assert sum(1 for m in plan.reply_msgs if m["content"] == message) == 1

    # Non-streamed and streamed both consume that one list.
    await run_turn(
        admin_message=message,
        record=OnboardingRecord(ask_beat="business_type", ask_count=1),
        provider=(non_streamed := _ExtractFake(updates=[{}], replies=["Noted."])),
    )
    assert sum(1 for m in non_streamed.chat_messages[0] if m["content"] == message) == 1

    streamed = _ExtractFake(updates=[{}], replies=["Noted."])
    stream_plan = await prepare_turn(
        admin_message=message,
        record=OnboardingRecord(ask_beat="business_type", ask_count=1),
        provider=streamed,
    )
    async for _event in stream_reply(plan=stream_plan, provider=streamed):
        pass
    assert sum(1 for m in streamed.stream_calls[0] if m["content"] == message) == 1


@pytest.mark.asyncio
async def test_an_em_dash_in_a_model_reply_becomes_a_plain_dash() -> None:
    """conventions.md 1 bans the em dash, and the live model emits them anyway.

    Both reply paths normalize, because the founder saw "Got it-open Monday" on
    the streamed one - the surface a prompt rule alone was supposed to protect.
    """

    def _turn() -> tuple[_ExtractFake, OnboardingRecord]:
        provider = _ExtractFake(
            updates=[{"profile": {"business_type": "Sababa"}, "answered_asked": True}],
            replies=["Got it\u2014Sababa it is."],
        )
        record = OnboardingRecord(
            draft={"owner_display_name": "Nikan", "business_name": "Sababa"},
            ask_beat="business_type",
            ask_count=1,
        )
        return provider, record

    provider, record = _turn()
    _updated, reply = await run_turn(admin_message="Sababa", record=record, provider=provider)
    assert "\u2014" not in reply
    assert reply.startswith("Got it - Sababa it is.")

    provider, record = _turn()
    plan = await prepare_turn(admin_message="Sababa", record=record, provider=provider)
    streamed = "".join(
        [
            payload
            async for kind, payload in stream_reply(plan=plan, provider=provider)
            if kind == "token"
        ]
    )
    assert "\u2014" not in streamed
    assert "Got it - Sababa it is." in streamed


# --- URL turn (O-3 site-as-shortcut) -------------------------------------------


@pytest.mark.asyncio
async def test_prepare_url_turn_extracts_from_page_and_reads_back() -> None:
    provider = _ExtractFake(
        updates=[
            {
                "profile": {
                    "business_type": "phone repair shop",
                    "services": "screen repairs, battery replacements",
                    "hours": "Mon-Fri 9-6",
                }
            },
        ],
    )
    record = OnboardingRecord()
    plan = await prepare_url_turn(
        url="https://bytefix.example.com",
        page_text=(
            "Bytefix Repairs fixes phones. Screen repairs and battery "
            "replacements. Open weekdays 9 to 6."
        ),
        record=record,
        provider=provider,
    )

    assert plan.summary is not None
    assert "Here's what I've got from your site" in plan.summary
    assert "phone repair shop" in plan.summary
    assert "screen repairs" in plan.summary
    assert "Mon-Fri 9-6" in plan.summary
    assert plan.reply_msgs is None
    assert record.draft["business_type"] == "phone repair shop"


@pytest.mark.asyncio
async def test_prepare_url_turn_records_url_not_page_text() -> None:
    provider = _ExtractFake(updates=[{"profile": {"services": "screen repairs"}}])
    record = OnboardingRecord()
    plan = await prepare_url_turn(
        url="https://bytefix.example.com",
        page_text="a very long page that should never land in history",
        record=record,
        provider=provider,
    )

    user_messages = [m["content"] for m in plan.record.history if m["role"] == "user"]
    assert user_messages == ["https://bytefix.example.com"]
    assert "a very long page" not in plan.record.to_jsonb().__repr__()


@pytest.mark.asyncio
async def test_prepare_url_turn_reads_back_nothing_when_page_has_no_fields() -> None:
    provider = _ExtractFake(updates=[{"profile": None}])
    record = OnboardingRecord()
    plan = await prepare_url_turn(
        url="https://empty.example.com",
        page_text="welcome to my site",
        record=record,
        provider=provider,
    )

    assert plan.summary is not None
    assert "couldn't pin down" in plan.summary


@pytest.mark.asyncio
async def test_prepare_turn_keeps_explicit_offering_names_in_order_without_duplicates() -> None:
    provider = _ExtractFake(
        updates=[
            {
                "profile": {"owner_display_name": "Ronin"},
                "offering_names": ["Screen repair", "Battery swap", "screen repair", ""],
            }
        ]
    )
    plan = await prepare_turn(
        admin_message="We offer screen repair and battery swap",
        record=OnboardingRecord(),
        provider=provider,
    )
    assert [item.name for item in plan.record.offering_candidates] == [
        "Screen repair",
        "Battery swap",
    ]


def test_old_string_offerings_load_as_owner_candidates() -> None:
    record = OnboardingRecord.from_jsonb(
        {"version": 3, "offering_candidates": ["Coffee", "coffee"]}
    )
    assert record.offering_candidates == [PendingOffering(name="Coffee", sources=["owner"])]


# --- directive shape -----------------------------------------------------------
def test_the_copilot_contract_is_sectioned_and_states_every_prohibition() -> None:
    """W-9 US-5: the rules the live reproduction broke are structural, not phrasing.

    Each assertion below names a failure the founder's own drives produced, so
    a future rewrite of this prompt cannot quietly drop one of them.
    """
    assert "Agencx setup assistant" in _COPILOT
    for section in (
        "# ROLE",
        "# GOAL",
        "# SUCCESS CRITERIA",
        "# CONSTRAINTS",
        "# CONVERSATION RULES",
        "# OUTPUT",
        "# STOP RULES",
    ):
        assert section in _COPILOT
    # W-2: the model neither chooses nor phrases the question.
    assert "The server writes every question" in _COPILOT
    assert "Do not ask a question" in _COPILOT
    # No praise, no fabricated enthusiasm, no "no worries" (findings 2 and 3).
    assert "No praise" in _COPILOT
    assert '"no worries"' in _COPILOT
    # The name under discussion is the owner's (finding 2).
    assert 'Never write "my name"' in _COPILOT
    # One sentence, spelled as the owner spelled it (finding 1).
    assert "One sentence" in _COPILOT
    assert "character for character" in _COPILOT
    # C-1: no model-authored money, anywhere, ever.
    assert "Never state a price" in _COPILOT
    # I8: no vertical the owner did not name (finding 4).
    assert "Never name a trade" in _COPILOT
    # conventions.md 1 (observation 4 of the reproduction).
    assert "Never use an em dash" in _COPILOT
    assert "becomes a reference" in _KNOWLEDGE_OFFER


def test_onboarding_beats_use_soft_prototype_aligned_questions() -> None:
    assert beats.BEATS["business_name"].ask == "What does the business go by?"
    # W-7: the name beat says which name it wants, so it cannot be mistaken for
    # the business-name question.
    assert "call you" in beats.BEATS["owner_display_name"].ask
    # W-5/US-5 covered both halves; W-7 keeps that in one plain question.
    assert beats.BEATS["hours"].ask == "What days and hours are you open?"
    assert beats.BEATS["abn"].ask == "Do you have an ABN?"


def test_directive_as_prompt_with_acknowledged() -> None:
    """W-9 US-6: the brief carries the captured value, not just its label.

    The model cannot repeat a spelling it was never shown, and the reply check
    that enforces the spelling has nothing to check against either.
    """
    prompt = Directive(acknowledged=[("business name", "Sababa")]).as_prompt()
    assert "business name" in prompt
    assert '"Sababa"' in prompt
    assert "Repeat each value exactly" in prompt
    assert "Do not ask a question" in prompt


def test_directive_meta_answer() -> None:
    prompt = Directive(meta_answer="I'm here to help.").as_prompt()
    assert "Briefly answer" in prompt


def test_directive_never_asks_the_model_for_a_question() -> None:
    """W-2/W-7: no directive, however shaped, invites the model to compose the ask."""
    for directive in (
        Directive(),
        Directive(reask="Give an example."),
        Directive(handoff="Say you'll come back to it."),
        Directive(meta_answer="x"),
    ):
        prompt = directive.as_prompt()
        assert "Ask for" not in prompt
        assert "Do not ask a question" in prompt


# --- W-2: two asks per beat, then resolve or defer ------------------------------


def _drafted(**fields: str) -> OnboardingRecord:
    return OnboardingRecord(draft=dict(fields))


@pytest.mark.asyncio
async def test_a_filled_slot_is_never_re_asked() -> None:
    """W-2 US-1: the founder's transcript, as a regression test.

    `business_name` was captured, yet the reply asked for it again three times
    because the model composed the question. The question is now the server's.
    """
    provider = _ExtractFake(
        updates=[{"off_topic": True, "meta_reply": "I'm your setup assistant."}],
        replies=["I'm your setup assistant. What's the name of your business?"],
    )
    record = _drafted(owner_display_name="Nikan", business_name="Sababa")
    _updated, reply = await run_turn(
        admin_message="i already told u", record=record, provider=provider
    )

    assert reply.endswith(beats.BEATS["business_type"].ask)
    assert "What does the business go by?" not in reply


@pytest.mark.asyncio
async def test_an_off_beat_answer_is_captured_and_the_pending_question_stands() -> None:
    """W-2 US-2: naming offerings while asked about hours fills services, not hours."""
    provider = _ExtractFake(
        updates=[{"offering_names": ["pita", "coffee", "wraps"]}],
        replies=["Pita, coffee and wraps - noted."],
    )
    record = _drafted(
        owner_display_name="Nikan",
        business_name="Sababa",
        business_type="cafe",
        headcount="just me",
    )
    updated, reply = await run_turn(
        admin_message="pita coffee wraps and more", record=record, provider=provider
    )

    assert [item.name for item in updated.offering_candidates] == ["pita", "coffee", "wraps"]
    assert updated.draft["services"] == "pita, coffee, wraps"
    # The pending beat is still the one that gets asked.
    assert reply.endswith(beats.BEATS["hours"].ask)


@pytest.mark.asyncio
async def test_a_skippable_beat_takes_its_default_after_two_asks() -> None:
    """W-2 US-4: team size is read by nothing, so silence resolves to "just me"."""
    provider = _ExtractFake(updates=[{}, {}, {}], replies=["Sure."])
    record = _drafted(owner_display_name="Nikan", business_name="Sababa", business_type="cafe")

    for _ in range(2):
        record, reply = await run_turn(admin_message="dunno", record=record, provider=provider)
        assert reply.endswith(beats.BEATS["headcount"].ask)
    assert record.ask_count == 2

    record, reply = await run_turn(admin_message="dunno", record=record, provider=provider)

    assert record.draft["headcount"] == "just me"
    assert reply.endswith(beats.BEATS["hours"].ask)


@pytest.mark.asyncio
async def test_a_required_beat_is_deferred_rather_than_asked_a_third_time() -> None:
    """W-2 US-4: the interview keeps moving; the beat comes back at the end."""
    provider = _ExtractFake(updates=[{}, {}, {}], replies=["Sure."])
    record = _drafted(owner_display_name="Nikan")

    for _ in range(3):
        record, reply = await run_turn(admin_message="pass", record=record, provider=provider)

    assert record.deferred == ["business_name"]
    # Moved on rather than repeating a third time.
    assert reply.endswith(beats.BEATS["business_type"].ask)
    assert record.draft.get("business_name", "") == ""


def test_a_deferred_beat_returns_only_once_every_other_beat_is_done() -> None:
    """W-2: two passes, so a repeat is never adjacent to itself."""
    draft = _complete_draft()
    del draft["business_name"]
    del draft["hours"]

    # With `hours` still open, the deferred business_name stays held back.
    held = beats.next_beat(draft, (), ["business_name"])
    assert held is not None and held.key == "hours"

    draft["hours"] = "9-5 weekdays"
    returned = beats.next_beat(draft, (), ["business_name"])
    assert returned is not None and returned.key == "business_name"


@pytest.mark.asyncio
async def test_the_final_pass_pauses_without_saving_an_unusable_answer() -> None:
    """W-7 leaves an unresolved required field empty and blocks go-live."""
    provider = _ExtractFake(updates=[{}, {}, {}], replies=["Right."])
    draft = _complete_draft()
    del draft["business_type"]
    record = OnboardingRecord(draft=draft, deferred=["business_type"])

    for _ in range(3):
        record, _reply = await run_turn(
            admin_message="idk just a shop", record=record, provider=provider
        )

    assert "business_type" not in record.draft
    assert record.paused_beat == "business_type"
    assert not request_finalize(record.draft, record.skipped).ok


def test_resume_paused_beat_restores_the_question_and_two_ask_allowance() -> None:
    record = OnboardingRecord(
        draft={"owner_display_name": "Nikan", "business_name": "Sababa"},
        deferred=["business_type"],
        paused_beat="business_type",
    )

    reply = resume_paused_beat(record)

    assert record.paused_beat is None
    assert (record.ask_beat, record.ask_count) == ("business_type", 1)
    assert reply.endswith(beats.BEATS["business_type"].ask)


@pytest.mark.asyncio
async def test_the_opening_question_validates_its_first_answer() -> None:
    provider = _ExtractFake(
        updates=[{"profile": {"owner_display_name": "34234234"}, "answered_asked": True}],
        replies=["Let's try that again."],
    )

    record, reply = await run_turn(
        admin_message="34234234", record=OnboardingRecord(), provider=provider
    )

    assert "owner_display_name" not in record.draft
    assert record.ask_beat == "owner_display_name"
    assert record.ask_count == 2
    assert reply.endswith(beats.BEATS["owner_display_name"].ask)


# --- W-2: skipping --------------------------------------------------------------


def test_a_skipped_beat_is_never_asked_again_and_does_not_block_go_live() -> None:
    draft = _complete_draft()
    del draft["services"]

    open_beat = beats.next_beat(draft)
    assert open_beat is not None and open_beat.key == "services"
    assert beats.next_beat(draft, ["services"]) is None
    assert request_finalize(draft, ["services"]).ok


def test_skipping_writes_no_sentinel_into_the_public_profile() -> None:
    """A skip must not reach the storefront - `profile_tagline` renders these."""
    draft = _complete_draft()
    del draft["services"]
    record = OnboardingRecord(draft=draft, skipped=["services"])

    stored = record.to_jsonb()["draft"]
    assert "services" not in stored
    tagline = profile_tagline(stored) or ""
    assert "skip" not in tagline.lower()


def test_w2_record_fields_survive_a_round_trip_without_a_version_bump() -> None:
    """An in-flight interview must not be reset by this ticket's new fields."""
    record = OnboardingRecord(
        draft={"owner_display_name": "Sam"},
        skipped=["services"],
        deferred=["hours"],
        ask_beat="hours",
        ask_count=2,
    )
    restored = OnboardingRecord.from_jsonb(record.to_jsonb())

    assert restored.version == 4
    assert (restored.skipped, restored.deferred) == (["services"], ["hours"])
    assert (restored.ask_beat, restored.ask_count) == ("hours", 2)

    # A record written before W-2 loads clean rather than crashing.
    legacy = OnboardingRecord.from_jsonb({"version": 3, "draft": {"name": "Sam"}})
    assert legacy.skipped == [] and legacy.deferred == []
    assert legacy.draft == {"owner_display_name": "Sam"}


@pytest.mark.asyncio
async def test_a_turn_persists_even_when_extraction_returns_nothing() -> None:
    """W-2: the stored record and the emitted state can never disagree."""
    provider = _ExtractFake(updates=[{}], replies=["Sure."])
    record = _drafted(owner_display_name="Sam")

    updated, _reply = await run_turn(admin_message="hmm", record=record, provider=provider)

    assert [entry["role"] for entry in updated.history] == ["user", "assistant"]


def test_the_extraction_prompt_shows_how_to_split_a_comma_less_list() -> None:
    """W-2 US-3: "we offer A B and C" is three candidates, not one.

    W-9 I8: the example teaches the split with placeholder items. It used to
    teach it in one vertical's vocabulary ("pita coffee and wraps"), which is
    the same leak the services beat's own example had.
    """
    assert '["A", "B", "C"]' in _EXTRACT_PROMPT
    assert "Split a run-on list" in _EXTRACT_PROMPT
    # Whole words only: "capitalization" contains "pita", and the rule that
    # protects the owner's own capitalization is exactly what this prompt gained.
    words = set(re.findall(r"[a-z]+", _EXTRACT_PROMPT.lower()))
    for trade in ("pita", "wraps", "haircut", "haircuts", "dental"):
        assert trade not in words
    assert "phone repair" not in _EXTRACT_PROMPT.lower()


# --- W-7: input validation, rejection, and the spoken hand-off -----------------


def test_beat_validity_accepts_real_answers_and_rejects_junk() -> None:
    """W-7: `valid` is the server's half of the two-judge usability check."""
    assert beats.BEATS["owner_display_name"].valid("Nikan")  # type: ignore[misc]
    assert not beats.BEATS["owner_display_name"].valid("34234234")  # type: ignore[misc]
    assert beats.BEATS["business_name"].valid("Sababa")  # type: ignore[misc]
    assert not beats.BEATS["business_name"].valid("9999")  # type: ignore[misc]
    assert beats.BEATS["hours"].valid("9-5 Mon to Fri")  # type: ignore[misc]
    assert beats.BEATS["hours"].valid("online, always open")  # type: ignore[misc]
    assert not beats.BEATS["hours"].valid("asdf")  # type: ignore[misc]
    assert beats.BEATS["contact"].valid("me@example.com")  # type: ignore[misc]
    assert beats.BEATS["contact"].valid("0412 345 678")  # type: ignore[misc]
    assert not beats.BEATS["contact"].valid("yes")  # type: ignore[misc]


def test_usable_needs_both_judges() -> None:
    """Either the LLM verdict or the server check can veto (W-7)."""
    name = beats.BEATS["owner_display_name"]
    assert _usable(name, "Nikan", answered_asked=True)
    # Server floor: a number is not a name even if the model waved it through.
    assert not _usable(name, "34234234", answered_asked=True)
    # LLM catches word-shaped nonsense the regex passes.
    assert not _usable(beats.BEATS["business_type"], "asdfgh", answered_asked=False)
    # answered_asked None (no beat asked) does not veto on its own.
    assert _usable(name, "Nikan", answered_asked=None)


def test_ack_keeps_the_statement_and_drops_a_trailing_question() -> None:
    assert _ack("Nice to meet you, Sam! What's your name?") == "Nice to meet you, Sam!"
    assert _ack("Got it.") == "Got it."
    assert _ack("What's your name?") == ""


def test_no_beat_offers_a_skip_chip() -> None:
    """W-7 removed the skip chip; nothing may reintroduce a skip-valued chip."""
    for beat in beats.BEAT_ORDER:
        for chip in beats.input_spec(beat).chips:
            assert chip.value != "__skip__"
            assert chip.label != "Skip for now"


def test_hours_beat_asks_one_question() -> None:
    assert beats.BEATS["hours"].ask.count("?") == 1


@pytest.mark.asyncio
async def test_a_junk_answer_is_dropped_and_the_beat_is_re_asked() -> None:
    """W-7: "34234234" for a name is not saved; the same beat is asked again."""
    provider = _ExtractFake(
        updates=[{"profile": {"owner_display_name": "34234234"}}],
        replies=["Hmm, that doesn't read like a name."],
    )
    record = OnboardingRecord(ask_beat="owner_display_name", ask_count=1)
    updated, reply = await run_turn(admin_message="34234234", record=record, provider=provider)

    # The value never reaches the draft.
    assert "owner_display_name" not in updated.draft
    # The server re-appends the same beat's own question.
    assert reply.endswith(beats.BEATS["owner_display_name"].ask)
    # W-9: the whole reply is the beat's own words - no model call is made, so
    # there is nothing for a model to embellish the beat's example into.
    assert reply == (
        f"{beats.BEATS['owner_display_name'].reject} {beats.BEATS['owner_display_name'].ask}"
    )
    assert provider.chat_messages == []


@pytest.mark.asyncio
async def test_word_shaped_nonsense_is_rejected_by_the_llm_verdict() -> None:
    """The regex passes "asdfgh"; the extractor's verdict is what vetoes it."""
    provider = _ExtractFake(
        updates=[{"profile": {"business_type": "asdfgh"}, "answered_asked": False}],
        replies=["Let's try that again."],
    )
    record = OnboardingRecord(
        draft={"owner_display_name": "Nikan", "business_name": "Sababa"},
        ask_beat="business_type",
        ask_count=1,
    )
    updated, reply = await run_turn(admin_message="asdfgh", record=record, provider=provider)

    assert "business_type" not in updated.draft
    assert reply.endswith(beats.BEATS["business_type"].ask)


@pytest.mark.asyncio
async def test_a_genuine_answer_is_accepted_and_advances() -> None:
    provider = _ExtractFake(
        updates=[{"profile": {"owner_display_name": "Nikan"}, "answered_asked": True}],
        replies=["Lovely to meet you, Nikan."],
    )
    record = OnboardingRecord(ask_beat="owner_display_name", ask_count=1)
    updated, reply = await run_turn(admin_message="Nikan", record=record, provider=provider)

    # W-9: a usable name is proposed first; agreeing is what advances the beat.
    assert reply == 'I have "Nikan". Is that right?'
    updated, reply = await run_turn(admin_message="yes", record=updated, provider=provider)

    assert updated.draft["owner_display_name"] == "Nikan"
    # It moves on to the next beat rather than re-asking.
    assert reply.endswith(beats.BEATS["business_name"].ask)


@pytest.mark.asyncio
async def test_two_junk_answers_hand_off_out_loud_to_the_next_beat() -> None:
    """W-7: after two asks a required beat defers, and the assistant says so."""
    provider = _ExtractFake(
        updates=[{"profile": {"business_name": "@@@@"}}],
        replies=["No problem at all."],
    )
    # Already asked twice; this third junk reply trips the hand-off.
    record = OnboardingRecord(
        draft={"owner_display_name": "Nikan"}, ask_beat="business_name", ask_count=2
    )
    updated, reply = await run_turn(admin_message="@@@@", record=record, provider=provider)

    # The required beat is deferred, not dropped, and not saved with junk.
    assert "business_name" in updated.deferred
    assert "business_name" not in updated.draft
    # The next beat is asked, and the deferred beat's question is not repeated.
    assert reply.endswith(beats.BEATS["business_type"].ask)
    assert beats.BEATS["business_name"].ask not in reply
    # The model was handed the hand-off line to phrase.
    directive = provider.chat_messages[-1][1]["content"]
    assert "come back" in directive


@pytest.mark.asyncio
async def test_an_off_topic_turn_burns_no_ask() -> None:
    provider = _ExtractFake(
        updates=[{"off_topic": True, "meta_reply": "I set up your assistant."}],
        replies=["Happy to explain."],
    )
    record = OnboardingRecord(
        draft={"owner_display_name": "Nikan"}, ask_beat="business_name", ask_count=1
    )
    updated, _reply = await run_turn(
        admin_message="what are you?", record=record, provider=provider
    )

    # The ask counter does not advance on noise.
    assert updated.ask_count == 1
    assert "business_name" not in updated.deferred


def test_merge_offerings_lets_the_document_win_an_overlap() -> None:
    """W-7: an owner-typed name and a priced document candidate become one row,
    keeping the document's price and description; sources record both."""
    from app.onboarding.flow import merge_offerings

    owner = PendingOffering(name="Flat white", sources=["owner"])
    document = PendingOffering(
        name="Flat White", description="Our house blend", price_cents=550, sources=["document"]
    )
    merged = merge_offerings(owner, document)

    assert merged.price_cents == 550
    assert merged.description == "Our house blend"
    assert merged.name == "Flat White"
    assert set(merged.sources) == {"owner", "document"}


@pytest.mark.asyncio
async def test_an_owner_name_merges_with_a_document_candidate_keeping_its_price() -> None:
    provider = _ExtractFake(updates=[{"offering_names": ["Flat white"]}])
    record = OnboardingRecord(
        offering_candidates=[
            PendingOffering(name="Flat White", price_cents=550, sources=["document"])
        ]
    )
    plan = await prepare_turn(admin_message="we do flat white", record=record, provider=provider)

    candidates = plan.record.offering_candidates
    assert len(candidates) == 1
    assert candidates[0].price_cents == 550
    assert set(candidates[0].sources) == {"owner", "document"}


@pytest.mark.asyncio
async def test_junk_the_model_calls_off_topic_is_still_challenged() -> None:
    """W-7: "34234234" mislabeled off-topic is a failed name answer, not chatter.

    The server catches it (the raw message cannot be a name) and routes the
    challenge, rather than answering it as a stray question and re-asking blandly.
    """
    provider = _ExtractFake(
        updates=[{"off_topic": True, "meta_reply": "I'm your setup assistant."}],
        replies=["That doesn't read like a name."],
    )
    record = OnboardingRecord(ask_beat="owner_display_name", ask_count=1)
    updated, reply = await run_turn(admin_message="34234234", record=record, provider=provider)

    assert "owner_display_name" not in updated.draft
    assert reply.endswith(beats.BEATS["owner_display_name"].ask)
    # It counts as a failed answer, so the ask advances toward the cap.
    assert updated.ask_count == 2
    # The challenge is the beat's own reject line, not a model paraphrase of it.
    assert reply.startswith(beats.BEATS["owner_display_name"].reject)
    assert provider.chat_messages == []


@pytest.mark.asyncio
async def test_a_real_off_topic_question_is_still_answered_not_challenged() -> None:
    """A genuine question ("what are you?") stays off-topic and burns no ask."""
    provider = _ExtractFake(
        updates=[{"off_topic": True, "meta_reply": "I set up your assistant."}],
        replies=["Happy to explain."],
    )
    record = OnboardingRecord(ask_beat="owner_display_name", ask_count=1)
    updated, _reply = await run_turn(
        admin_message="what are you?", record=record, provider=provider
    )

    assert updated.ask_count == 1  # not burned


# --- W-9: name confirmation, corrections, offerings, voice, reply check --------


def _draft_up_to(key: str) -> dict[str, Any]:
    """A draft holding every beat before ``key``, so ``key`` is what is asked."""
    complete = _complete_draft()
    draft: dict[str, Any] = {}
    for beat in beats.BEAT_ORDER:
        if beat.key == key:
            return draft
        draft[beat.key] = complete[beat.key]
    raise AssertionError(f"{key} is not a beat")


@pytest.mark.asyncio
async def test_a_confirmed_name_is_assigned_never_concatenated() -> None:
    """W-9 US-1, the founder's `sababa` fixture: `sababa` confirmed is `sababa`.

    The raw input sits beside the proposal as evidence of what was typed. The
    reproduction's ``Sababasababa`` is what appending one to the other looks
    like, so the commit path is asserted to assign.
    """
    record = OnboardingRecord(
        pending_name={"target": "owner_display_name", "raw": "sababa", "proposal": "sababa"}
    )

    assert confirm_pending_name(record) == "sababa"
    assert record.draft["owner_display_name"] == "sababa"
    assert record.pending_name is None


@pytest.mark.asyncio
async def test_a_typed_reply_to_a_proposal_is_a_new_proposal_not_a_rejection() -> None:
    """W-9 US-1: correcting the spelling proposes the correction, and costs
    nothing at the beat that is waiting."""
    provider = _ExtractFake(
        updates=[{"profile": {"owner_display_name": "Sababa"}, "answered_asked": True}],
        replies=["Noted."],
    )
    record = OnboardingRecord(
        pending_name={"target": "owner_display_name", "raw": "sababa", "proposal": "sababa"},
        ask_beat="owner_display_name",
        ask_count=1,
    )
    updated, reply = await run_turn(admin_message="Sababa", record=record, provider=provider)

    assert updated.pending_name is not None
    assert updated.pending_name["proposal"] == "Sababa"
    assert "owner_display_name" not in updated.draft
    assert reply == 'I have "Sababa". Is that right?'
    assert (updated.ask_beat, updated.ask_count) == ("owner_display_name", 1)
    # The extractor is told what is waiting, so a respelling is not read as an
    # answer to some other field.
    assert 'owner_display_name = "sababa"' in provider.extract_inputs[0]


def test_a_pending_proposal_survives_a_reload() -> None:
    """W-9 US-1: reloading mid-confirmation resumes the same proposal."""
    record = OnboardingRecord(
        draft={"owner_display_name": "Sam"},
        pending_name={
            "target": "business_name",
            "raw": "we are sababa",
            "proposal": "Sababa",
        },
    )
    restored = OnboardingRecord.from_jsonb(record.to_jsonb())

    assert restored.pending_name == record.pending_name
    stage, spec, can_confirm = progress(restored)
    assert (stage, can_confirm) == ("business_name", False)
    assert spec is not None
    assert [chip.label for chip in spec.chips] == ["Yes"]


def test_a_v3_record_carries_no_proposal_and_a_v4_one_round_trips() -> None:
    assert OnboardingRecord.from_jsonb({"version": 3, "draft": {}}).pending_name is None
    assert OnboardingRecord.from_jsonb({"version": 4, "pending_name": {}}).pending_name is None


@pytest.mark.asyncio
async def test_junk_never_becomes_the_public_identity_without_a_yes() -> None:
    """W-9 US-1, the founder's `21 ej2nek2ne2ken1e` fixture.

    It contains a word, so the server's own `valid` waves it through - which is
    exactly why confirmation, not a stricter regex, is the interception point.
    In the reproduction it became the business name, the go-live read-back, and
    the suggested address `agencx.app/21-ej2nek2ne2ken1e`.
    """
    junk = "21 ej2nek2ne2ken1e"
    provider = _ExtractFake(
        updates=[{"profile": {"business_name": junk}, "answered_asked": True}],
        replies=["Noted."],
    )
    record = OnboardingRecord(
        draft={"owner_display_name": "Nikan"}, ask_beat="business_name", ask_count=1
    )
    updated, reply = await run_turn(admin_message=junk, record=record, provider=provider)

    assert "business_name" not in updated.draft
    assert reply == f'I have "{junk}". Is that right?'
    assert junk not in _activation_summary(updated.draft)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "asked",
    ["headcount", "hours", "services", "customer_voice_preset", "contact", "abn", "gst"],
)
async def test_a_correction_applies_from_whatever_beat_is_on_screen(asked: str) -> None:
    """W-9 US-3: a correction is not an answer to the pending question.

    The reproduction's `middle eastern cafe`, typed while the headcount beat was
    pending, landed nowhere at all - not in a field, not in the reply.
    """
    provider = _ExtractFake(
        updates=[
            {
                "corrections": [
                    {
                        "field": "business_type",
                        "value": "middle eastern cafe",
                        "raw": "middle eastern cafe",
                        "normalization": "none",
                    }
                ]
            }
        ],
        replies=["Noted."],
    )
    record = OnboardingRecord(draft=_draft_up_to(asked), ask_beat=asked, ask_count=1)
    updated, reply = await run_turn(
        admin_message="middle eastern cafe", record=record, provider=provider
    )

    assert updated.draft["business_type"] == "middle eastern cafe"
    # The pending question keeps both its place and its remaining attempt.
    assert (updated.ask_beat, updated.ask_count) == (asked, 1)
    # And the corrected value is read back once, so it can be corrected again.
    assert "middle eastern cafe" in reply
    # An accepted correction is part of the record a reload restores.
    assert OnboardingRecord.from_jsonb(updated.to_jsonb()).draft["business_type"] == (
        "middle eastern cafe"
    )


@pytest.mark.asyncio
async def test_an_invalid_correction_keeps_the_previous_value() -> None:
    """W-9 US-3: the value already on file beats one the server cannot read."""
    provider = _ExtractFake(
        updates=[{"corrections": [{"field": "contact", "value": "yes", "raw": "yes"}]}],
        replies=["Noted."],
    )
    draft = _draft_up_to("abn")
    record = OnboardingRecord(draft=dict(draft), ask_beat="abn", ask_count=1)
    updated, _reply = await run_turn(admin_message="yes", record=record, provider=provider)

    assert updated.draft["contact"] == draft["contact"]
    assert (updated.ask_beat, updated.ask_count) == ("abn", 1)


@pytest.mark.asyncio
async def test_an_unusable_answer_restores_what_it_overwrote() -> None:
    """W-9 US-3: the rejection path used to pop a value with no memory of what
    it replaced, so a bad overwrite destroyed a good answer."""
    provider = _ExtractFake(
        updates=[{"profile": {"hours": "asdf"}, "answered_asked": False}],
        replies=["Noted."],
    )
    record = OnboardingRecord(
        draft=_draft_up_to("services") | {"hours": "Mon-Fri 9-6"},
        ask_beat="hours",
        ask_count=1,
    )
    updated, _reply = await run_turn(admin_message="asdf", record=record, provider=provider)

    assert updated.draft["hours"] == "Mon-Fri 9-6"


@pytest.mark.asyncio
async def test_an_ambiguous_name_correction_is_asked_about_not_guessed() -> None:
    """W-9 US-2: "change the name" with both names on file asks which."""
    provider = _ExtractFake(
        updates=[{"corrections": [{"field": "unresolved_name", "value": ""}]}],
        replies=["Noted."],
    )
    record = OnboardingRecord(
        draft={"owner_display_name": "Sam", "business_name": "Bytefix Repairs"},
        ask_beat="business_type",
        ask_count=1,
    )
    updated, reply = await run_turn(
        admin_message="change the name", record=record, provider=provider
    )

    assert reply.endswith("Which name should I change - your own, or the business's?")
    assert updated.draft["owner_display_name"] == "Sam"
    assert updated.draft["business_name"] == "Bytefix Repairs"
    # No model composed that question, and nothing was guessed at.
    assert provider.chat_messages == []


@pytest.mark.asyncio
async def test_an_unambiguous_name_correction_resolves_and_is_confirmed() -> None:
    """With only one name on file there is nothing to disambiguate - but the
    correction is still a proposal, not a write."""
    provider = _ExtractFake(
        updates=[
            {"corrections": [{"field": "unresolved_name", "value": "Sababa Cafe", "raw": "sababa"}]}
        ],
        replies=["Noted."],
    )
    record = OnboardingRecord(
        draft={"business_name": "Sababa"}, ask_beat="business_type", ask_count=1
    )
    updated, reply = await run_turn(
        admin_message="change the name to sababa cafe", record=record, provider=provider
    )

    assert reply == 'I have "Sababa Cafe". Is that right?'
    assert updated.draft["business_name"] == "Sababa"
    assert confirm_pending_name(updated) == "Sababa Cafe"
    assert updated.draft["business_name"] == "Sababa Cafe"


def _priced_candidate() -> PendingOffering:
    return PendingOffering(
        name="Screen repair",
        description="Aftermarket screen, same day",
        price_cents=12900,
        sources=["document"],
        source_references=[
            SourceReference(
                block="b1", excerpt="Screen repair - same day", supported_fields=["name"]
            )
        ],
        price_note="from",
        needs_review=True,
        price_options=[12900, 17900],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "expected"),
    [
        ({"op": "add", "name": "Battery swap"}, ["Screen repair", "Battery swap"]),
        (
            {"op": "rename", "name": "Screen repair", "new_name": "Screen replacement"},
            ["Screen replacement"],
        ),
        ({"op": "remove", "name": "Screen repair"}, []),
        (
            {"op": "replace", "name": "Screen repair", "new_name": "Back glass repair"},
            ["Back glass repair"],
        ),
    ],
)
async def test_the_four_offering_operations_are_distinct(
    operation: dict[str, str], expected: list[str]
) -> None:
    """W-9 US-4: add, rename, remove and replace each mean their own thing."""
    provider = _ExtractFake(updates=[{"offering_ops": [operation]}], replies=["Noted."])
    record = OnboardingRecord(
        draft=_draft_up_to("customer_voice_preset"),
        offering_candidates=[_priced_candidate()],
        ask_beat="customer_voice_preset",
        ask_count=1,
    )
    updated, _reply = await run_turn(
        admin_message="change what we offer", record=record, provider=provider
    )

    assert [item.name for item in updated.offering_candidates] == expected


@pytest.mark.asyncio
async def test_a_rename_preserves_every_provenance_field() -> None:
    """W-9 US-4: a rename changes the name. W-6's provenance survives it."""
    original = _priced_candidate()
    provider = _ExtractFake(
        updates=[
            {
                "offering_ops": [
                    {"op": "rename", "name": "Screen repair", "new_name": "Screen replacement"}
                ]
            }
        ],
        replies=["Noted."],
    )
    record = OnboardingRecord(
        draft=_draft_up_to("customer_voice_preset"),
        offering_candidates=[original],
        ask_beat="customer_voice_preset",
        ask_count=1,
    )
    updated, _reply = await run_turn(
        admin_message="call it a screen replacement", record=record, provider=provider
    )

    renamed = updated.offering_candidates[0]
    assert renamed.name == "Screen replacement"
    assert renamed.model_dump(exclude={"name"}) == original.model_dump(exclude={"name"})


@pytest.mark.asyncio
async def test_an_offering_edit_costs_no_attempt_at_the_pending_question() -> None:
    provider = _ExtractFake(
        updates=[{"offering_ops": [{"op": "remove", "name": "Screen repair"}]}],
        replies=["Noted."],
    )
    record = OnboardingRecord(
        draft=_draft_up_to("contact"),
        offering_candidates=[_priced_candidate()],
        ask_beat="contact",
        ask_count=1,
    )
    updated, _reply = await run_turn(
        admin_message="drop the screen repair", record=record, provider=provider
    )

    assert (updated.ask_beat, updated.ask_count) == ("contact", 1)


# --- W-9 US-5: the deterministic reply check ----------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("bad_reply", "why"),
    [
        ("I'm a real person, so I'll take care of that.", "claims to be a person"),
        ("Your AI assistant has that noted.", "names itself an AI"),
        ("It's just me running the shop.", "answers the question about to be asked"),
        ("my name is noted.", "inverts the pronoun"),
        ("That runs about $99.", "states an amount"),
        ("Noted, a phone shop.", "does not repeat the captured spelling"),
    ],
)
async def test_a_reply_that_fails_the_check_is_replaced_by_the_server(
    bad_reply: str, why: str
) -> None:
    """W-9 US-5: every one of these is a failure the reproduction produced or
    the ticket names. The replacement is the server's own words - the model is
    never asked again, so W-7's latency decision stands."""
    provider = _ExtractFake(
        updates=[{"profile": {"business_type": "phone repair shop"}, "answered_asked": True}],
        replies=[bad_reply, bad_reply],
    )
    record = OnboardingRecord(
        draft=_draft_up_to("business_type"), ask_beat="business_type", ask_count=1
    )
    _updated, reply = await run_turn(
        admin_message="we fix phones", record=record, provider=provider
    )

    assert reply == (
        "Got business type: phone repair shop. Is it just you, or do you work with a team?"
    ), why
    # One reply call, or two when the price echo guard redrafted - never more.
    assert len(provider.chat_messages) <= 2


@pytest.mark.asyncio
async def test_a_reply_that_passes_the_check_is_kept_verbatim() -> None:
    provider = _ExtractFake(
        updates=[{"profile": {"business_type": "phone repair shop"}, "answered_asked": True}],
        replies=["Noted, a phone repair shop."],
    )
    record = OnboardingRecord(
        draft=_draft_up_to("business_type"), ask_beat="business_type", ask_count=1
    )
    _updated, reply = await run_turn(
        admin_message="we fix phones", record=record, provider=provider
    )

    assert reply == "Noted, a phone repair shop. Is it just you, or do you work with a team?"


@pytest.mark.asyncio
async def test_the_streamed_path_retracts_a_reply_that_fails_the_check() -> None:
    """The streamed surface uses the redraft event it already has, and the
    replacement is server-composed rather than a second model pass."""
    provider = _ExtractFake(
        updates=[{"profile": {"business_type": "phone repair shop"}, "answered_asked": True}],
        replies=["It's just me running the shop."],
    )
    record = OnboardingRecord(
        draft=_draft_up_to("business_type"), ask_beat="business_type", ask_count=1
    )
    plan = await prepare_turn(admin_message="we fix phones", record=record, provider=provider)
    events = [event async for event in stream_reply(plan=plan, provider=provider)]

    assert ("redraft", "reply_check") in events
    shown = "".join(payload for kind, payload in events if kind == "token")
    assert shown.endswith(
        "Got business type: phone repair shop. Is it just you, or do you work with a team?"
    )
    assert len(provider.stream_calls) == 1


@pytest.mark.asyncio
async def test_a_rejected_beat_reads_back_what_it_did_capture() -> None:
    """W-9: failing the pending beat and volunteering something else in one
    message must not lose the something else - one acknowledgement, no model."""
    provider = _ExtractFake(
        updates=[
            {
                "profile": {"hours": "@@@@"},
                "corrections": [
                    {"field": "business_type", "value": "middle eastern cafe", "raw": "cafe"}
                ],
                "answered_asked": False,
            }
        ],
        replies=["Noted."],
    )
    record = OnboardingRecord(draft=_draft_up_to("hours"), ask_beat="hours", ask_count=1)
    _updated, reply = await run_turn(
        admin_message="@@@@ - we're a middle eastern cafe", record=record, provider=provider
    )

    assert reply == (
        "Got business type: middle eastern cafe. I couldn't read that as opening hours. "
        "What days and hours are you open?"
    )
    assert provider.chat_messages == []


# --- W-9 US-7: the voice beat -------------------------------------------------


def test_the_voice_beat_follows_services_and_offers_four_chips() -> None:
    order = [beat.key for beat in beats.BEAT_ORDER]
    assert order[order.index("services") + 1] == "customer_voice_preset"

    beat = beats.BEATS["customer_voice_preset"]
    assert [chip.value for chip in beat.chips] == [
        "warm_casual",
        "clear_professional",
        "direct_concise",
        "custom",
    ]
    # The fourth swaps the composer instead of answering by itself.
    assert [chip.widget for chip in beat.chips] == [None, None, None, "text"]
    # I8: nothing in the question or its chips names a trade.
    assert "sound" in beat.ask


def test_a_voice_preset_and_a_custom_description_are_validated_server_side() -> None:
    draft: dict[str, Any] = {}
    assert beats.apply_selection(draft, "customer_voice_preset", ["clear_professional"]) == (
        "Clear and professional"
    )
    assert draft == {"customer_voice_preset": "clear_professional"}

    described = "plain and unhurried, like talking over the counter"
    assert beats.apply_selection(draft, "customer_voice_preset", [described]) == described
    assert draft["customer_voice_preset"] == "custom"
    assert draft["customer_voice_custom_style"] == described

    # Choosing a preset afterwards clears the description it replaces.
    beats.apply_selection(draft, "customer_voice_preset", ["direct_concise"])
    assert "customer_voice_custom_style" not in draft

    # Bounded, so a voice cannot become a second system prompt.
    with pytest.raises(ValueError, match="valid answer"):
        beats.apply_selection(draft, "customer_voice_preset", ["x" * (CUSTOM_VOICE_MAX + 1)])
    # Tapping the chip submits nothing - its own value is not a description.
    with pytest.raises(ValueError, match="valid answer"):
        beats.apply_selection(draft, "customer_voice_preset", ["custom"])


def test_no_model_can_write_the_voice_fields() -> None:
    """W-9: the voice is server-owned, and the extractor is not told it exists."""
    draft: dict[str, Any] = {}
    save_profile(
        draft,
        ProfileDraft(customer_voice_preset="direct_concise", customer_voice_custom_style="terse"),
    )
    assert draft == {}
    for field in ("customer_voice_preset", "customer_voice_custom_style"):
        assert field not in _EXTRACT_PROMPT


@pytest.mark.asyncio
async def test_a_typed_voice_is_captured_by_the_server_not_the_model() -> None:
    provider = _ExtractFake(updates=[{}], replies=["should not be called"])
    record = OnboardingRecord(
        draft=_draft_up_to("customer_voice_preset"),
        ask_beat="customer_voice_preset",
        ask_count=1,
    )
    described = "friendly but brief"
    updated, reply = await run_turn(admin_message=described, record=record, provider=provider)

    assert updated.draft["customer_voice_preset"] == "custom"
    assert updated.draft["customer_voice_custom_style"] == described
    assert reply == "Got it. How should customers reach you?"
    assert provider.chat_messages == []


def test_the_stored_voice_has_the_shape_the_customer_assistant_reads() -> None:
    assert customer_voice_for(ProfileDraft()) == {"preset": "warm_casual", "custom_style": None}
    assert customer_voice_for(ProfileDraft(customer_voice_preset="direct_concise")) == {
        "preset": "direct_concise",
        "custom_style": None,
    }
    assert customer_voice_for(
        ProfileDraft(customer_voice_preset="custom", customer_voice_custom_style="warm and brief")
    ) == {"preset": "custom", "custom_style": "warm and brief"}
    # A description left behind by an earlier custom choice never rides along
    # with a preset that is not custom.
    assert customer_voice_for(
        ProfileDraft(customer_voice_preset="warm_casual", customer_voice_custom_style="ignore me")
    ) == {"preset": "warm_casual", "custom_style": None}


# --- W-9: the founder's five regression inputs --------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("junk", ["211e2esdsdfasdf", "bkksbf88", "21 ej2nek2ne2ken1e"])
async def test_a_junk_name_is_never_persisted_unconfirmed(junk: str) -> None:
    """The three junk fixtures, on the beat each of them reached in the drive."""
    provider = _ExtractFake(
        updates=[{"profile": {"owner_display_name": junk}, "answered_asked": True}],
        replies=["Noted."],
    )
    record = OnboardingRecord(ask_beat="owner_display_name", ask_count=1)
    updated, reply = await run_turn(admin_message=junk, record=record, provider=provider)

    assert "owner_display_name" not in updated.draft
    assert reply == f'I have "{junk}". Is that right?'
    # Nothing in the reply is the beat's own example read back as this owner.
    assert "Nikan" not in reply
