"""Demo world seed: both tenants, auth users, membership, and realistic
conversations/escalations/costs - the data behind docs/DEMO.md's walkthrough.

Run with ``uv run python -m seeds.seed_demo`` (after scripts/demo.sh has
started GoTrue + the DB). It is wipe-and-recreate idempotent: re-running
resets the whole demo world to a known state.

Structure (mirrors seeds/seed_tenant1_phoneshop.py's pattern):

1. Bytefix (Tenant 1) via ``seed_tenant1_phoneshop.seed`` - its existing
   wipe+recreate (config, 15 items, 12 rules, 20 orders, 3 docs).
2. Three GoTrue auth users (find-or-create by email), via an injected
   ``create_auth_user`` callable so tests run GoTrue-free with deterministic
   UUIDs. The default calls the GoTrue Admin API (POST /auth/v1/admin/users
   with a service_role bearer, email_confirm=true).
3. Lumident Dental (Tenant 2, slug ``lumident``, config only - pure demo
   data, explicitly NOT the T-037 generalization proof which has its own
   ticket). Distinct brand accent + dental-language customer config, ~8
   catalog items, ~6 pricing rules, ~6 appointment orders, 2 knowledge docs.
4. Membership rows: ``users`` (role='owner') for each tenant's owner;
   ``platform_admins`` for the founder. Tenant wipe cascades users;
   platform_admins is delete-then-insert by user_id for idempotency.
5. Conversations with explicit ``created_at`` (``now()`` is constant within
   one transaction and ``tenant_context`` is one transaction, so every
   insert sets created_at explicitly - spread over the past 7 days, messages
   5-30s apart so list/transcript ordering and the cost attribution lateral
   join all behave). 5 for bytefix (2 closed, 1 open, 2 escalated), 2 for
   lumident. Tool calls on 3 assistant messages, inspection verdicts in
   messages.metadata (the shape TraceTree.tsx renders), cost_logs placed just
   after each assistant message's created_at, and 3 escalations (open,
   claimed, resolved with a trailing human_agent message) respecting the
   0011 partial unique index.

Domain-agnosticism is data-side only: bytefix and lumident run identical
code and differ only in tenant_config + uploaded knowledge - no vertical
branches anywhere (the hard rule).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import httpx

from app.core import db
from app.core.config import get_settings
from app.ingestion.pipeline import ingest_catalog_items, process_document
from app.llm.embedder import Embedder, get_embedder
from seeds import seed_tenant1_phoneshop
from seeds.supabase_keys import mint_key

if TYPE_CHECKING:
    from app.core.db import AppConnection

# Demo identities (password ``wren-demo`` for all; 6+ chars satisfies GoTrue's
# default minimum). Kept here as the single source of truth for the demo
# banner, docs/DEMO.md, and the tests' fake create_auth_user.
BYTEFIX_OWNER_EMAIL = "owner@bytefix.dev"
LUMIDENT_OWNER_EMAIL = "owner@lumident.dev"
FOUNDER_EMAIL = "founder@wren.dev"
DEMO_PASSWORD = "wren-demo"

# Lumident (Tenant 2) - a dental practice. Pure demo data.
LUMIDENT_SLUG = "lumident"
LUMIDENT_NAME = "Lumident Dental"

LUMIDENT_CATALOG: list[tuple[str, str, int | None]] = [
    ("New Patient Exam", "Comprehensive exam, oral cancer screening, treatment plan", 9500),
    ("Standard Cleaning", "Routine professional cleaning and polish", 12000),
    ("Deep Cleaning (Per Quadrant)", "Scaling and root planing, one quadrant", 35000),
    ("Tooth-Colored Filling", "Composite resin filling, one surface", 25000),
    ("In-Office Whitening", "Single-session professional whitening", 45000),
    ("Dental Crown", "Porcelain-fused-to-metal crown, one tooth", 110000),
    ("Root Canal", "Endodontic treatment, one tooth", 95000),
    ("Emergency Visit", "Same-day pain or trauma assessment", 15000),
]

LUMIDENT_PRICING_RULES: list[tuple[str, str, int, str]] = [
    ("new-patient-exam", "New patient comprehensive exam", 9500, "each"),
    ("standard-cleaning", "Routine cleaning and polish", 12000, "each"),
    ("deep-cleaning-quadrant", "Deep cleaning - one quadrant", 35000, "each"),
    ("filling-composite", "Tooth-colored composite filling - one surface", 25000, "each"),
    ("filling-additional-surface", "Each additional surface on the same tooth", 9000, "each"),
    ("crown-pfm", "Porcelain-fused-to-metal crown", 110000, "each"),
    ("root-canal", "Root canal therapy - one tooth", 95000, "each"),
    ("whitening-inoffice", "In-office whitening session", 45000, "flat"),
]

APPOINTMENT_STATUSES = ["scheduled", "confirmed", "completed", "cancelled", "no_show"]

LUMIDENT_SERVICES_MD = """# Dental Services

## Cleanings and Prevention

A standard professional cleaning is recommended every six months and includes
a full polish and a review of your home-care routine. For patients with
periodontal concerns, we offer deep cleanings (scaling and root planing) done
one quadrant at a time, usually across two visits. New patients start with a
comprehensive exam that includes an oral cancer screening and a personalized
treatment plan, so you know exactly what you need before anything is scheduled.

## Restorative Care

We place tooth-colored composite fillings for cavities, matched to your natural
shade. A single-surface filling is one price, and each additional surface on the
same tooth is a smaller add-on. For teeth that need more structural support, we
place porcelain-fused-to-metal crowns, which take two visits: a prep visit with
a temporary, then a final cementation once the lab finishes the crown.

## Cosmetic and Emergency

Our in-office whitening is a single one-hour session that lifts several shades
in one visit. For dental emergencies - severe pain, a knocked-out tooth, or a
broken crown - we keep same-day slots open every day; call ahead and we will fit
you in. Emergency visits cover the assessment and pain relief; further treatment
is quoted separately.
"""

LUMIDENT_FAQ_MD = """# Frequently Asked Questions

## Do you take walk-in emergencies?

Yes. We reserve same-day emergency slots every day for severe pain, trauma, or
a knocked-out tooth. Call ahead so we can prepare, but we will see you even if
you cannot reach us first. Save a knocked-out tooth in milk or saliva and bring
it with you - it can often be re-implanted within an hour.

## How often should I get a cleaning?

Every six months for most patients. Patients with gum disease or a history of
heavy buildup may be advised to come every three to four months instead. Your
hygienist will tell you what interval fits your mouth, not a generic schedule.

## Does whitening damage enamel?

Professional in-office whitening does not damage enamel when done correctly. You
may experience temporary sensitivity for a day or two, which resolves on its
own. We do not recommend over-the-counter kits for patients with existing
sensitivity without a quick consult first.

## What if I am anxious about the dentist?

We are used to nervous patients and will never rush you. Tell us at booking and
we will schedule extra time, explain each step before we do it, and offer breaks
whenever you need them. Sedation options are available for longer procedures if
you and the dentist agree they are appropriate.
"""

CreateAuthUser = Callable[[str, str], Awaitable[UUID]]


# --- GoTrue Admin API: the default create_auth_user (tests inject a fake) -------


def _make_gotrue_create_auth_user() -> CreateAuthUser:
    """Build the default create_auth_user from settings (GoTrue Admin API).

    Find-or-create by email: list existing admin users first (the demo has
    very few), return the id on a match, otherwise POST a new confirmed user.
    The Admin API is used instead of direct auth-schema SQL because the auth
    schema is GoTrue-owned and version-drifting - hand-inserting rows requires
    bcrypt-via-pgcrypto, instance_id, aud, role, identities rows, etc. and is
    the classic source of "seeded user can't log in" breakage.
    """
    settings = get_settings()
    base = settings.supabase_url.rstrip("/")
    secret = settings.supabase_jwt_secret
    if not base or not secret:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_JWT_SECRET must be set to seed demo auth "
            "users (run scripts/demo.sh, or inject create_auth_user in tests)."
        )
    service_token = mint_key("service_role", secret)
    headers = {
        "Authorization": f"Bearer {service_token}",
        "apikey": service_token,
        "Content-Type": "application/json",
    }

    async def create_auth_user(email: str, password: str) -> UUID:
        async with httpx.AsyncClient(timeout=30) as client:
            # Find existing by email (admin list). Handle both the
            # {"users": [...]} object shape and the bare-array shape GoTrue
            # has used across versions.
            found = await _gotrue_find_user_by_email(client, base, headers, email)
            if found is not None:
                return found
            resp = await client.post(
                f"{base}/auth/v1/admin/users",
                json={"email": email, "password": password, "email_confirm": True},
                headers=headers,
            )
            if resp.status_code in (200, 201):
                return UUID(str(resp.json()["id"]))
            # A concurrent create (or a stale list cache) can race; re-scan
            # before giving up so a rerun during a partial failure still wins.
            found = await _gotrue_find_user_by_email(client, base, headers, email)
            if found is not None:
                return found
            resp.raise_for_status()
            raise RuntimeError(  # pragma: no cover - raise_for_status covers it
                f"unexpected GoTrue admin create response: {resp.status_code}"
            )

    return create_auth_user


async def _gotrue_find_user_by_email(
    client: httpx.AsyncClient,
    base: str,
    headers: dict[str, str],
    email: str,
) -> UUID | None:
    page = 1
    while True:
        resp = await client.get(
            f"{base}/auth/v1/admin/users",
            params={"page": page, "per_page": 1000},
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
        users = data.get("users", []) if isinstance(data, dict) else data
        for user in users:
            if user.get("email") == email and user.get("id"):
                return UUID(str(user["id"]))
        # Stop when no more pages.
        if isinstance(data, dict):
            if not data.get("has_next") or not users:
                break
        elif not users:
            break
        page += 1
    return None


# --- Lumident (Tenant 2) --------------------------------------------------------


async def _wipe_lumident(conn: AppConnection) -> None:
    existing_id = await conn.fetchval("select id from tenants where slug = $1", LUMIDENT_SLUG)
    if existing_id is not None:
        await conn.execute("delete from tenants where id = $1", existing_id)


async def _seed_lumident_core() -> UUID:
    tenant_id = uuid4()
    async with db.tenant_context(None, "service") as conn:
        await conn.execute(
            "insert into tenants (id, slug, name, status) values ($1, $2, $3, 'active')",
            tenant_id,
            LUMIDENT_SLUG,
            LUMIDENT_NAME,
        )
        await conn.execute(
            "insert into tenant_config (tenant_id, tone, escalation_threshold, brand, config) "
            "values ($1, 'professional', 0.5, $2, $3)",
            tenant_id,
            json.dumps({"display_name": LUMIDENT_NAME, "accent": "#2C7A7B"}),
            json.dumps(
                {
                    "customer": {
                        "greeting": (
                            "Hello, and welcome to Lumident Dental. I can help you "
                            "understand a treatment, estimate a procedure's cost, or "
                            "check an upcoming appointment - how can I help?"
                        ),
                        "starter_questions": [
                            "How much is a standard cleaning?",
                            "What does a tooth-colored filling cost?",
                            "Do you take walk-in emergencies?",
                        ],
                    }
                }
            ),
        )

    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        for name, description, price_cents in LUMIDENT_CATALOG:
            await conn.execute(
                "insert into catalog_items (tenant_id, name, description, price_cents) "
                "values ($1, $2, $3, $4)",
                tenant_id,
                name,
                description,
                price_cents,
            )
        for code, label, unit_amount_cents, unit in LUMIDENT_PRICING_RULES:
            await conn.execute(
                "insert into pricing_rules (tenant_id, code, label, unit_amount_cents, unit) "
                "values ($1, $2, $3, $4, $5)",
                tenant_id,
                code,
                label,
                unit_amount_cents,
                unit,
            )
        for i in range(6):
            await conn.execute(
                "insert into orders (tenant_id, ref_code, kind, customer_ref, status, details) "
                "values ($1, $2, 'appointment', $3, $4, $5)",
                tenant_id,
                f"APPT-{3001 + i}",
                f"patient-{i + 1}",
                APPOINTMENT_STATUSES[i % len(APPOINTMENT_STATUSES)],
                json.dumps({"provider": "dr-lumident", "duration_min": 45}),
            )
    return tenant_id


async def _seed_lumident_knowledge(tenant_id: UUID, embedder: Embedder) -> None:
    uploads_dir = Path(get_settings().uploads_dir) / str(tenant_id)
    uploads_dir.mkdir(parents=True, exist_ok=True)
    docs = [
        ("services.md", "other", LUMIDENT_SERVICES_MD),
        ("faq.md", "faq", LUMIDENT_FAQ_MD),
    ]
    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        for filename, doc_type, content in docs:
            document_id = uuid4()
            (uploads_dir / f"{document_id}.md").write_text(content)
            await conn.execute(
                "insert into documents (id, tenant_id, filename, doc_type, status) "
                "values ($1, $2, $3, $4, 'pending')",
                document_id,
                tenant_id,
                filename,
                doc_type,
            )
            await process_document(
                conn, tenant_id=tenant_id, document_id=document_id, embedder=embedder
            )
        await ingest_catalog_items(conn, tenant_id=tenant_id, embedder=embedder)


# --- Membership: users + platform_admins ---------------------------------------


async def _seed_membership(
    bytefix_id: UUID,
    bytefix_owner: UUID,
    lumident_id: UUID,
    lumident_owner: UUID,
    founder: UUID,
) -> None:
    async with db.tenant_context(bytefix_id, "tenant_admin") as conn:
        await conn.execute(
            "insert into users (id, tenant_id, role) values ($1, $2, 'owner')",
            bytefix_owner,
            bytefix_id,
        )
    async with db.tenant_context(lumident_id, "tenant_admin") as conn:
        await conn.execute(
            "insert into users (id, tenant_id, role) values ($1, $2, 'owner')",
            lumident_owner,
            lumident_id,
        )
    # platform_admins is not tenant-scoped and survives a tenant wipe, so
    # delete-then-insert by user_id for idempotency (matches test_auth_api's
    # _insert_platform_admin RLS-with-check pattern under platform_admin role).
    async with db.tenant_context(None, "platform_admin") as conn:
        await conn.execute("delete from platform_admins where user_id = $1", founder)
        await conn.execute("insert into platform_admins (user_id) values ($1)", founder)


# --- Conversations, messages, tool calls, costs, escalations -------------------


def _demo_model() -> str:
    return get_settings().llm_model or "demo-model"


# Each conversation is seeded with explicit created_at timestamps so ordering
# and the cost lateral join (which brackets by created_at) are deterministic.
# A _SeedConv is inserted inside one tenant_context transaction.
def _bytefix_conversations(now: datetime) -> list[dict[str, Any]]:
    return [
        {
            "customer_ref": "alex.rivera",
            "status": "closed",
            "created_at": now - timedelta(days=7),
            "messages": [
                ("customer", "How much to replace the screen on a Galaxy S21?", None, None, 0),
                (
                    "assistant",
                    "A standard aftermarket screen replacement for the Galaxy S21 is $129, "
                    "or $179 if you'd prefer an original OEM display. Both are same-day. "
                    "Would you like me to put together a quote?",
                    "quoting",
                    {
                        "inspection": {
                            "grounding": {
                                "passed": True,
                                "reason": (
                                    "Price figures match the pricing engine quote line items."
                                ),
                            },
                            "policy": {
                                "passed": True,
                                "reason": "Friendly, offers next step.",
                            },
                        }
                    },
                    12,
                ),
            ],
            "tool_calls": [
                {
                    "on_message_index": 1,
                    "tool_name": "get_quote_inputs",
                    "arguments": {"rule_codes": ["screen-repair-flagship-aftermarket"]},
                    "result": {
                        "line_items": [
                            {"code": "screen-repair-flagship-aftermarket", "quantity": 1}
                        ]
                    },
                    "success": True,
                    "latency_ms": 38,
                }
            ],
            "escalation": None,
        },
        {
            "customer_ref": "sam.lee",
            "status": "closed",
            "created_at": now - timedelta(days=5),
            "messages": [
                ("customer", "Is there a warranty on your repairs?", None, None, 0),
                (
                    "assistant",
                    "Yes - every repair is covered by a 90-day warranty against defects in parts "
                    "and workmanship [1]. If the same issue recurs within that window, we'll fix "
                    "it at no charge [1].",
                    "knowledge",
                    {
                        "inspection": {
                            "grounding": {
                                "passed": True,
                                "reason": "Both claims trace to the warranty section of policy.md.",
                            },
                            "injection": {
                                "passed": True,
                                "reason": "No injected instructions detected.",
                            },
                        }
                    },
                    15,
                ),
                ("customer", "Can I speak to a manager about a previous visit?", None, None, 22),
                (
                    "human_agent",
                    "Of course - I'll review your visit and call you back this afternoon. "
                    "Thanks for reaching out.",
                    None,
                    None,
                    30,
                ),
            ],
            "tool_calls": [
                {
                    "on_message_index": 1,
                    "tool_name": "search_knowledge",
                    "arguments": {"query": "warranty on repairs"},
                    "result": {"chunks": ["policy.md#warranty"]},
                    "success": True,
                    "latency_ms": 52,
                }
            ],
            "escalation": {"reason": "Customer asked to speak to a manager.", "status": "resolved"},
        },
        {
            "customer_ref": "jordan.patel",
            "status": "open",
            "created_at": now - timedelta(days=3),
            "messages": [
                ("customer", "Where's my repair? The ticket is R-1001.", None, None, 0),
                (
                    "assistant",
                    "I found it - repair R-1001 is currently in progress and we expect it to be "
                    "ready for pickup later today. We'll text you the moment it's finished.",
                    "order_status",
                    {
                        "inspection": {
                            "grounding": {
                                "passed": True,
                                "reason": "Status matches the orders row.",
                            }
                        }
                    },
                    10,
                ),
            ],
            "tool_calls": [
                {
                    "on_message_index": 1,
                    "tool_name": "lookup_order_or_ticket",
                    "arguments": {"ref_code": "R-1001"},
                    "result": {
                        "found": True,
                        "ref_code": "R-1001",
                        "status": "in_progress",
                        "kind": "repair",
                    },
                    "success": True,
                    "latency_ms": 21,
                }
            ],
            "escalation": None,
        },
        {
            "customer_ref": "casey.nguyen",
            "status": "escalated",
            "created_at": now - timedelta(days=2),
            "messages": [
                ("customer", "I'd really like to talk to a human about this.", None, None, 0),
                (
                    "assistant",
                    "No problem - I'm handing you to a human teammate who'll follow up shortly. "
                    "Thanks for your patience.",
                    "escalation",
                    {
                        "inspection": {
                            "grounding": {"passed": True, "reason": "No factual claims to verify."}
                        }
                    },
                    8,
                ),
            ],
            "tool_calls": [],
            "escalation": {"reason": "Customer asked for a human.", "status": "open"},
        },
        {
            "customer_ref": "morgan.chen",
            "status": "escalated",
            "created_at": now - timedelta(days=1),
            "messages": [
                (
                    "customer",
                    "This is the third time my screen has broken after your repair. I'm furious.",
                    None,
                    None,
                    0,
                ),
                (
                    "assistant",
                    "I'm really sorry to hear that - that's frustrating, and "
                    "I want to make it right. "
                    "I'm escalating this to a senior technician right now so "
                    "we can look into what's "
                    "happening and get it sorted.",
                    "escalation",
                    {
                        "inspection": {
                            "grounding": {
                                "passed": True,
                                "reason": "Empathy + escalation, no facts invented.",
                            }
                        }
                    },
                    14,
                ),
            ],
            "tool_calls": [],
            "escalation": {
                "reason": "Angry repeat customer; sentiment-driven escalation.",
                "status": "claimed",
            },
        },
    ]


def _lumident_conversations(now: datetime) -> list[dict[str, Any]]:
    return [
        {
            "customer_ref": "patient.a",
            "status": "closed",
            "created_at": now - timedelta(days=4),
            "messages": [
                (
                    "customer",
                    "How much is a standard cleaning if I'm a new patient?",
                    None,
                    None,
                    0,
                ),
                (
                    "assistant",
                    "A standard cleaning is $120. As a new patient you'd also start with a $95 "
                    "comprehensive exam, which includes an oral cancer screening and a treatment "
                    "plan. Would you like me to quote both together?",
                    "quoting",
                    {
                        "inspection": {
                            "grounding": {
                                "passed": True,
                                "reason": "Prices match the catalog and pricing engine.",
                            }
                        }
                    },
                    11,
                ),
            ],
            "tool_calls": [
                {
                    "on_message_index": 1,
                    "tool_name": "get_quote_inputs",
                    "arguments": {"rule_codes": ["standard-cleaning", "new-patient-exam"]},
                    "result": {
                        "line_items": [
                            {"code": "standard-cleaning", "quantity": 1},
                            {"code": "new-patient-exam", "quantity": 1},
                        ]
                    },
                    "success": True,
                    "latency_ms": 33,
                }
            ],
            "escalation": None,
        },
        {
            "customer_ref": "patient.b",
            "status": "open",
            "created_at": now - timedelta(days=2, hours=6),
            "messages": [
                ("customer", "Do you take walk-in emergencies?", None, None, 0),
                (
                    "assistant",
                    "Yes - we reserve same-day emergency slots every day for severe pain, trauma, "
                    "or a knocked-out tooth. Call ahead if you can, but we'll "
                    "see you either way [1].",
                    "knowledge",
                    {
                        "inspection": {
                            "grounding": {
                                "passed": True,
                                "reason": "Matches the FAQ's emergency entry.",
                            }
                        }
                    },
                    13,
                ),
            ],
            "tool_calls": [],
            "escalation": None,
        },
    ]


async def _seed_conversations(
    conn: AppConnection,
    tenant_id: UUID,
    specs: list[dict[str, Any]],
) -> None:
    model = _demo_model()
    for spec in specs:
        conv_id = uuid4()
        created_at = spec["created_at"]
        assert isinstance(created_at, datetime)
        await conn.execute(
            "insert into conversations (id, tenant_id, customer_ref, channel, status, created_at) "
            "values ($1, $2, $3, 'web', $4, $5)",
            conv_id,
            tenant_id,
            spec["customer_ref"],
            spec["status"],
            created_at,
        )

        messages: list[tuple[str, str, str | None, dict[str, Any] | None, int]] = spec["messages"]
        message_ids: list[UUID] = []
        msg_time = created_at
        for role, content, agent_node, metadata, offset in messages:
            msg_time = created_at + timedelta(seconds=offset)
            msg_id = uuid4()
            message_ids.append(msg_id)
            await conn.execute(
                "insert into messages (id, tenant_id, conversation_id, role, content, "
                "agent_node, created_at, metadata) "
                "values ($1, $2, $3, $4, $5, $6, $7, $8)",
                msg_id,
                tenant_id,
                conv_id,
                role,
                content,
                agent_node,
                msg_time,
                json.dumps(metadata) if metadata is not None else "{}",
            )
            # A cost_log for every assistant turn, placed just after the
            # message's created_at so the lateral-join window in
            # conversations.py attributes it to this message.
            if role == "assistant":
                cost_time = msg_time + timedelta(seconds=2)
                await conn.execute(
                    "insert into cost_logs (tenant_id, conversation_id, model, "
                    "input_tokens, output_tokens, cost_usd, created_at) "
                    "values ($1, $2, $3, $4, $5, $6, $7)",
                    tenant_id,
                    conv_id,
                    model,
                    1200,
                    180,
                    0.0021,
                    cost_time,
                )

        for tc in spec.get("tool_calls", []):
            target_msg = message_ids[tc["on_message_index"]]
            tc_id = uuid4()
            await conn.execute(
                "insert into tool_calls (id, tenant_id, message_id, tool_name, arguments, "
                "result, success, latency_ms, created_at) "
                "values ($1, $2, $3, $4, $5, $6, $7, $8, $9)",
                tc_id,
                tenant_id,
                target_msg,
                tc["tool_name"],
                json.dumps(tc["arguments"]),
                json.dumps(tc["result"]),
                tc["success"],
                tc["latency_ms"],
                # Place the tool call a hair before the assistant message it
                # belongs to (the assistant turn follows the tool result).
                created_at + timedelta(seconds=tc["on_message_index"]) - timedelta(seconds=1),
            )

        escalation: dict[str, Any] | None = spec.get("escalation")
        if escalation is not None:
            esc_id = uuid4()
            esc_created = created_at + timedelta(seconds=16)
            status = escalation["status"]
            resolved_at = None
            if status == "resolved":
                # Resolved escalation: resolved_at set, and the trailing
                # human_agent message (last in the spec) is the resolution reply.
                resolved_at = msg_time + timedelta(seconds=30)
            await conn.execute(
                "insert into escalations (id, tenant_id, conversation_id, reason, status, "
                "created_at, resolved_at) values ($1, $2, $3, $4, $5, $6, $7)",
                esc_id,
                tenant_id,
                conv_id,
                escalation["reason"],
                status,
                esc_created,
                resolved_at,
            )


# --- The top-level seed ---------------------------------------------------------


async def seed(
    embedder: Embedder | None = None,
    create_auth_user: CreateAuthUser | None = None,
) -> dict[str, UUID]:
    """Seed (or re-seed) the whole demo world. Returns the tenant + user ids.

    ``create_auth_user`` defaults to the GoTrue Admin API client built from
    ``settings``; tests inject a fake returning deterministic UUIDs so the
    full seed runs GoTrue-free.
    """
    created_pool = False
    try:
        db.get_pool()
    except RuntimeError:
        await db.create_pool()
        created_pool = True

    try:
        resolved_embedder = embedder or get_embedder(get_settings())
        user_factory = create_auth_user or _make_gotrue_create_auth_user()

        # 1. Bytefix (wipes + recreates tenant 'bytefix' with a fresh id).
        bytefix_id = await seed_tenant1_phoneshop.seed(embedder=resolved_embedder)
        print(f"seeded bytefix (tenant_id={bytefix_id})")

        # 2. Auth users (find-or-create by email).
        bytefix_owner = await user_factory(BYTEFIX_OWNER_EMAIL, DEMO_PASSWORD)
        lumident_owner = await user_factory(LUMIDENT_OWNER_EMAIL, DEMO_PASSWORD)
        founder = await user_factory(FOUNDER_EMAIL, DEMO_PASSWORD)
        print(
            f"auth users: owner@bytefix={bytefix_owner} "
            f"owner@lumident={lumident_owner} founder={founder}"
        )

        # 3. Lumident (Tenant 2) - wipe + recreate, config + catalog + knowledge.
        async with db.tenant_context(None, "platform_admin") as conn:
            await _wipe_lumident(conn)
        lumident_id = await _seed_lumident_core()
        await _seed_lumident_knowledge(lumident_id, resolved_embedder)
        print(f"seeded lumident (tenant_id={lumident_id})")

        # 4. Membership rows.
        await _seed_membership(bytefix_id, bytefix_owner, lumident_id, lumident_owner, founder)
        print("seeded membership (2 owners + 1 platform admin)")

        # 5. Conversations, tool calls, costs, escalations.
        now = datetime.now(UTC)
        async with db.tenant_context(bytefix_id, "tenant_admin") as conn:
            await _seed_conversations(conn, bytefix_id, _bytefix_conversations(now))
        async with db.tenant_context(lumident_id, "tenant_admin") as conn:
            await _seed_conversations(conn, lumident_id, _lumident_conversations(now))
        print("seeded conversations (5 bytefix + 2 lumident), tool calls, costs, escalations")

        print(
            "\ndemo world ready. Logins (password wren-demo):\n"
            f"  tenant console: http://app.localhost:3000/login  {BYTEFIX_OWNER_EMAIL}\n"
            f"  tenant console: http://app.localhost:3000/login  {LUMIDENT_OWNER_EMAIL}\n"
            f"  platform:       http://admin.localhost:3000      {FOUNDER_EMAIL}"
        )
        return {
            "bytefix_id": bytefix_id,
            "lumident_id": lumident_id,
            "bytefix_owner": bytefix_owner,
            "lumident_owner": lumident_owner,
            "founder": founder,
        }
    finally:
        if created_pool:
            await db.close_pool()


def main() -> None:
    asyncio.run(seed())


if __name__ == "__main__":
    main()
