"""T-037 / O-1: provision Tenant 2 (a dental clinic) through the public API.

The onboarding conversation portion pre-populates the lean v3 jsonb profile
directly (bypassing the LLM-driven copilot, per the 2026-07-30 decision), then
calls the confirm endpoint through the public API. The confirm validation and
write path is identical to a real admin's browser flow - only the state
population method differs.

Knowledge upload remains unchanged (real API calls). Since O-1 the profile
carries no prices: the clinic's fees reach the assistant through
``services-and-fees.md``, uploaded as a ``price_list`` document, which is the
only source a figure may be stated from (I1 / C-1).

``enabled_tools`` is deliberately NOT written here (D-2). The clinic takes the
column's lean default - search plus escalate - and that inheritance is the
point: tenant 1 opts into the commerce tools explicitly, tenant 2 touches
nothing, and the two run the same code. Writing the lean set here would prove
only that the seed can write, not that the default is right.

Usage::

    uv run python -m seeds.seed_tenant2_dental
    uv run python -m seeds.seed_tenant2_dental --teardown
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx

from app.shared import db
from app.shared.config import get_settings
from app.shared.voice import DEFAULT_VOICE_PRESET

INPUTS_DIR = Path(__file__).parent / "tenant2_inputs"
INTERVIEW_SCRIPT = INPUTS_DIR / "interview-script.md"

SLUG = "northgate"
TENANT_NAME = "Northgate Family Dental"
OWNER_EMAIL = "owner@northgate.test"
OWNER_PASSWORD = "wren-demo"

# (filename, doc_type) - doc_type must be in knowledge.ALLOWED_DOC_TYPES.
KNOWLEDGE_DOCS: tuple[tuple[str, str], ...] = (
    ("clinic-policies.md", "policy"),
    ("services-and-fees.md", "price_list"),
    ("faq.md", "faq"),
)

# One stage per lean profile field, in beat order (see BEAT_ORDER in
# app/onboarding/beats.py). These are the keys folded into the draft.
PROFILE_STAGES: tuple[str, ...] = (
    "owner_display_name",
    "business_name",
    "business_type",
    "headcount",
    "hours",
    "services",
    "contact",
)

# The stage names the script must cover. knowledge_prompt is not a data stage
# - it's the final prompt before confirm.
EXPECTED_STAGES: tuple[str, ...] = (*PROFILE_STAGES, "knowledge_prompt")

# Prose is allowed between a stage heading and its fenced answer, so the
# script stays readable as a document; only the fence is posted.
_STAGE_BLOCK_RE = re.compile(
    r"^## stage:\s*(?P<stage>\S+)\s*\n(?P<prose>(?:(?!^## ).)*?)```\n(?P<answer>.*?)\n```",
    re.MULTILINE | re.DOTALL,
)


def parse_interview_script(text: str) -> dict[str, str]:
    """Pull ``{stage: answer}`` out of interview-script.md."""
    found = {m.group("stage"): m.group("answer").strip() for m in _STAGE_BLOCK_RE.finditer(text)}
    missing = [stage for stage in EXPECTED_STAGES if stage not in found]
    if missing:
        raise ValueError(f"interview script is missing stages: {missing}")
    return found


def _build_draft_from_answers(answers: dict[str, str]) -> dict[str, Any]:
    """Construct a lean v3 profile draft from the raw text interview answers.

    This bypasses the LLM-driven copilot per the ADR. The keys match
    ``ProfileDraft`` in app/onboarding/flow.py exactly, so the confirm endpoint
    validates them identically to a real admin's browser flow. Every value is
    the owner's own free text - nothing here is dental-specific platform
    config, which is the point of the proof (I8).
    """
    draft = {stage: answers[stage].strip() for stage in PROFILE_STAGES}
    draft["business_name"] = draft["business_name"] or TENANT_NAME
    # W-9: the voice beat is answered by tapping a chip, not by free text, so
    # the script has no stage for it - the pre-populated draft takes the same
    # value an unanswered voice beat resolves to. Nothing dental about it (I8).
    draft["customer_voice_preset"] = DEFAULT_VOICE_PRESET
    return draft


class ProofFailure(RuntimeError):
    """A step the proof requires did not succeed through the public API."""


def _check(resp: httpx.Response, step: str) -> Any:
    if resp.status_code >= 400:
        raise ProofFailure(f"{step} failed: HTTP {resp.status_code} {resp.text}")
    return resp.json()


async def _create_owner_and_sign_in(client: httpx.AsyncClient, auth_base: str) -> str:
    """Create the clinic owner's auth user (if new) and return their access token.

    Signing up through GoTrue is what the real signup form does; the token
    that comes back is an ordinary user access token (aud=authenticated),
    the same one the browser would send.
    """
    signup = await client.post(
        f"{auth_base}/auth/v1/signup",
        json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD},
    )
    # 4xx here is almost always "user already registered" from a previous
    # run - fall through to the password grant rather than failing.
    if signup.status_code in (200, 201):
        token = signup.json().get("access_token")
        if token:
            return str(token)

    grant = await client.post(
        f"{auth_base}/auth/v1/token",
        params={"grant_type": "password"},
        json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD},
    )
    data = _check(grant, "owner sign-in")
    token = data.get("access_token")
    if not token:
        raise ProofFailure(f"sign-in returned no access_token: {data}")
    return str(token)


async def run_proof(api_base: str, auth_base: str) -> dict[str, Any]:
    answers = parse_interview_script(INTERVIEW_SCRIPT.read_text())
    report: dict[str, Any] = {"transcript": []}

    async with httpx.AsyncClient(timeout=180) as client:
        print(f"  owner auth user  {OWNER_EMAIL}")
        token = await _create_owner_and_sign_in(client, auth_base)
        headers = {"Authorization": f"Bearer {token}"}

        print(f"  signup           {SLUG}")
        signup = _check(
            await client.post(
                f"{api_base}/api/tenants",
                json={"slug": SLUG, "name": TENANT_NAME},
                headers=headers,
            ),
            "tenant signup",
        )
        report["tenant_id"] = signup["tenant_id"]

        # T-042 / O-1: pre-populate the lean v3 jsonb profile directly, bypassing
        # the LLM-driven copilot (per ADR in decisions-log.md). The confirm
        # endpoint gates and persists the draft identically to a real admin's
        # browser flow - only the state population method differs.
        print("  onboarding       pre-populating v3 profile")
        draft = _build_draft_from_answers(answers)
        # This is the one step that talks to the database rather than the API,
        # so it owns its own pool for the duration.
        await db.create_pool()
        try:
            async with db.tenant_context(UUID(signup["tenant_id"]), "tenant_admin") as conn:
                await conn.execute(
                    "update tenant_config set config = "
                    "jsonb_set(config, '{onboarding}', $2::jsonb, true), "
                    "updated_at = now() where tenant_id = $1",
                    UUID(signup["tenant_id"]),
                    json.dumps(
                        {
                            "version": 4,
                            "draft": draft,
                            "history": [],
                            "off_topic_count": 0,
                            "completed": False,
                        }
                    ),
                )
        finally:
            await db.close_pool()
        report["draft"] = draft

        print("  confirm")
        _check(
            await client.post(f"{api_base}/api/onboarding/confirm", headers=headers),
            "onboarding confirm",
        )

        report["documents"] = []
        for filename, doc_type in KNOWLEDGE_DOCS:
            print(f"  upload           {filename} ({doc_type})")
            body = (INPUTS_DIR / filename).read_bytes()
            uploaded = _check(
                await client.post(
                    f"{api_base}/api/knowledge/upload",
                    files={"file": (filename, body, "text/markdown")},
                    data={"doc_type": doc_type},
                    headers=headers,
                ),
                f"upload {filename}",
            )
            if uploaded["status"] != "ready":
                raise ProofFailure(
                    f"{filename} did not process: status={uploaded['status']} "
                    f"error={uploaded.get('error')}"
                )
            report["documents"].append(uploaded)

    return report


async def teardown() -> None:
    """Delete a previous proof run. NOT part of the proof - it only undoes one.

    Direct SQL is fine here precisely because this path is excluded from the
    proof: it exists so the provisioning run above can be repeated from a
    clean slate without hand-written psql.
    """
    from app.shared import db

    await db.create_pool()
    try:
        async with db.tenant_context(None, "platform_admin") as conn:
            tenant_id = await conn.fetchval("select id from tenants where slug = $1", SLUG)
            if tenant_id is None:
                print(f"nothing to tear down - no tenant {SLUG!r}")
                return
            await conn.execute("delete from users where tenant_id = $1", tenant_id)
            await conn.execute("delete from tenants where id = $1", tenant_id)
            print(f"tore down tenant {SLUG!r} ({tenant_id})")
    finally:
        await db.close_pool()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--teardown", action="store_true", help="remove a previous proof run")
    parser.add_argument("--api-base", default="http://localhost:8000")
    args = parser.parse_args()

    if args.teardown:
        asyncio.run(teardown())
        return 0

    auth_base = get_settings().supabase_url.rstrip("/")
    if not auth_base:
        print("SUPABASE_URL must be set (run scripts/demo.sh first).", file=sys.stderr)
        return 1

    print(f"provisioning tenant 2 through the public API at {args.api_base}")
    try:
        report = asyncio.run(run_proof(args.api_base, auth_base))
    except ProofFailure as exc:
        print(f"\nPROOF FAILED: {exc}", file=sys.stderr)
        print(
            "\nThis is a platform bug, not a script bug: every step above is a call the "
            "browser already makes for tenant 1. Fix the platform, then re-run.",
            file=sys.stderr,
        )
        return 1

    print(
        f"\ntenant {SLUG!r} is live: "
        f"{len(PROFILE_STAGES)} profile fields captured, "
        f"{len(report['documents'])} documents ingested"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
