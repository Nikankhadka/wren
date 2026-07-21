"""T-037: provision Tenant 2 (a dental clinic) through the public API only.

This is deliberately NOT a seed in the sense the other files in this
directory are. ``seed_tenant1_phoneshop`` and ``seed_demo`` write rows
directly; this one never touches the database. It drives exactly the calls a
real business owner's browser makes:

    POST /api/tenants            (signup - Surface 1)
    POST /api/onboarding/message x6   (the conversation - Surface 2)
    POST /api/onboarding/confirm      (go live)
    POST /api/knowledge/upload   x3   (the clinic's own documents)

That restriction *is* the proof. The platform's domain-agnostic rule
(AGENTS.md) says no code branches on a business vertical - so a dental
clinic must be reachable through the same doors a phone repair shop used,
with nothing dental-specific anywhere in the codebase. If this script ever
needs a direct write, a schema tweak, or a code branch to succeed, that is a
platform bug to fix rather than something to work around here.

Inputs live in ``seeds/tenant2_inputs/``: three knowledge documents the
clinic would actually own, and ``interview-script.md``, whose fenced blocks
are posted verbatim as the six onboarding answers.

Usage (needs the local stack up - ``scripts/demo.sh``, or db + auth +
backend running)::

    uv run python -m seeds.seed_tenant2_dental
    uv run python -m seeds.seed_tenant2_dental --teardown

``--teardown`` removes a previous run so the proof can be repeated from
zero. It is the one path in this file that touches the database directly,
and it is not part of the proof - it only undoes it.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path
from typing import Any

import httpx

from app.core.config import get_settings

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

# The stage names the script must cover, in the order the flow walks them.
EXPECTED_STAGES: tuple[str, ...] = (
    "identity",
    "tone",
    "services",
    "pricing_rules",
    "escalation_threshold",
    "knowledge_prompt",
)

# Prose is allowed between a stage heading and its fenced answer, so the
# script stays readable as a document; only the fence is posted.
_STAGE_BLOCK_RE = re.compile(
    r"^## stage:\s*(?P<stage>\S+)\s*\n(?P<prose>(?:(?!^## ).)*?)```\n(?P<answer>.*?)\n```",
    re.MULTILINE | re.DOTALL,
)


def parse_interview_script(text: str) -> dict[str, str]:
    """Pull ``{stage: answer}`` out of interview-script.md.

    The markdown file is the single source of truth so a human reading the
    proof sees exactly the words that were posted, with no second copy in
    Python to drift out of sync.
    """
    found = {m.group("stage"): m.group("answer").strip() for m in _STAGE_BLOCK_RE.finditer(text)}
    missing = [stage for stage in EXPECTED_STAGES if stage not in found]
    if missing:
        raise ValueError(f"interview script is missing stages: {missing}")
    return found


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

        # Walk the conversation exactly as the admin would: read the
        # assistant's prompt, answer it, repeat until the flow says confirm.
        state = _check(
            await client.get(f"{api_base}/api/onboarding/state", headers=headers),
            "onboarding state",
        )
        # A stage can legitimately repeat: the flow re-asks when an answer is
        # understood but incomplete (e.g. a pricing rule named with no
        # amount). The script supplies a `<stage>.followup` answer for that
        # second pass; a third pass means the flow is not converging.
        seen: dict[str, int] = {}
        while state["stage"] != "confirm":
            stage = state["stage"]
            seen[stage] = seen.get(stage, 0) + 1
            if seen[stage] == 1:
                answer = answers[stage]
            elif seen[stage] == 2 and f"{stage}.followup" in answers:
                answer = answers[f"{stage}.followup"]
            else:
                raise ProofFailure(
                    f"stage {stage!r} is not converging (asked {seen[stage]} times). "
                    f"Last prompt: {state['prompt']}"
                )
            print(f"  onboarding       {stage}" + (" (followup)" if seen[stage] > 1 else ""))
            report["transcript"].append(
                {"stage": stage, "prompt": state["prompt"], "answer": answer}
            )
            state = _check(
                await client.post(
                    f"{api_base}/api/onboarding/message",
                    json={"text": answer},
                    headers=headers,
                ),
                f"onboarding message ({stage})",
            )
        report["draft"] = state["draft"]

        print("  confirm")
        confirmed = _check(
            await client.post(f"{api_base}/api/onboarding/confirm", headers=headers),
            "onboarding confirm",
        )
        report["catalog_items_created"] = confirmed["catalog_items_created"]
        report["pricing_rules_created"] = confirmed["pricing_rules_created"]

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
    from app.core import db

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
        f"{report['catalog_items_created']} catalog items, "
        f"{report['pricing_rules_created']} pricing rules, "
        f"{len(report['documents'])} documents ingested"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
