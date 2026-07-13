"""Tenant 1 (anchor) seed: Bytefix Repairs, a phone repair shop.

Not owned by any single phase-1 ticket's file list, but required by T-010's
golden retrieval set (docs/design/database.md's seeds section fully
specifies this script's contents; see .agents/memory.md's T-010 entry for
why it's created here rather than earlier).

Idempotent: re-running wipes and recreates tenant 'bytefix' from scratch, so
eval runs always start from the same known state rather than accumulating
duplicate rows across reruns.

Usage: ``uv run python -m seeds.seed_tenant1_phoneshop``
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from app.core import db
from app.core.config import get_settings
from app.ingestion.pipeline import ingest_catalog_items, process_document
from app.llm.embedder import Embedder, get_embedder

if TYPE_CHECKING:
    from app.core.db import AppConnection

SLUG = "bytefix"
TENANT_NAME = "Bytefix Repairs"

# --- catalog_items: phones, accessories, tiered repair services (~15) -----------

CATALOG_ITEMS: list[tuple[str, str, int | None]] = [
    ("iPhone 11 (Refurbished, 64GB)", "Grade A refurbished, 90-day warranty", 24900),
    ("iPhone 12 (Refurbished, 128GB)", "Grade A refurbished, 90-day warranty", 34900),
    ("Samsung Galaxy S21 (Refurbished)", "Grade A refurbished, 90-day warranty", 29900),
    ("Google Pixel 6 (Refurbished)", "Grade A refurbished, 90-day warranty", 27900),
    ("Phone Case - Universal", "Shock-absorbing case, most models", 1500),
    ("Tempered Glass Screen Protector", "9H hardness, free installation", 1000),
    ("USB-C Charging Cable", "1 meter braided cable", 1200),
    ("Wall Charger Adapter", "20W fast-charging USB-C adapter", 1800),
    ("Screen Repair - Budget/Mid-range Android", "Aftermarket display, same-day", 5900),
    ("Screen Repair - Flagship (Aftermarket)", "Aftermarket display, same-day", 12900),
    ("Screen Repair - Flagship (OEM)", "Original display, same-day", 17900),
    ("Battery Replacement - Standard", "Most phone models, same-day", 4900),
    ("Battery Replacement - Flagship", "Larger-capacity flagship batteries", 6900),
    ("Charging Port Repair", "Loose or non-functioning charging port", 4500),
    ("Water Damage Diagnostic", "Assessment and cleaning, repair quoted separately", 3500),
]

# --- pricing_rules: agent-selectable rule codes (~12) ----------------------------

PRICING_RULES: list[tuple[str, str, int, str]] = [
    ("screen-repair-budget", "Screen repair - budget/mid Android", 5900, "each"),
    ("screen-repair-flagship-aftermarket", "Screen repair - flagship (aftermarket)", 12900, "each"),
    ("screen-repair-flagship-oem", "Screen repair - flagship (OEM)", 17900, "each"),
    ("battery-standard", "Battery replacement - standard", 4900, "each"),
    ("battery-flagship", "Battery replacement - flagship", 6900, "each"),
    ("charging-port-repair", "Charging port repair", 4500, "each"),
    ("water-damage-diagnostic", "Water damage diagnostic", 3500, "each"),
    ("camera-repair", "Camera module replacement", 5500, "each"),
    ("speaker-repair", "Speaker or microphone repair", 4000, "each"),
    ("back-glass-repair", "Back glass replacement", 6500, "each"),
    ("wireless-charging-coil", "Wireless charging coil replacement", 5500, "each"),
    ("rush-fee", "Rush service", 1500, "flat"),
]

REPAIR_STATUSES = ["pending", "in_progress", "ready_for_pickup", "completed", "cancelled"]
ORDER_STATUSES = ["pending", "shipped", "delivered"]

POLICY_MD = """# Repair Policies

## Warranty

Every repair we perform is covered by a 90-day warranty against defects in
parts and workmanship. If the same issue recurs within that window, we will
fix it again at no charge. The warranty does not cover new physical damage,
liquid damage that occurs after the repair, or issues caused by a
third-party repair performed after ours. Warranty coverage travels with the
device, not the original customer, so if you sell or gift the phone the new
owner is still covered for the remainder of the 90 days as long as they
have the original receipt.

## Turnaround Time

Most screen repairs and battery replacements are completed the same day,
usually within two to three hours of drop-off. Water damage assessments and
motherboard-level repairs can take three to five business days because they
require a diagnostic soak and component-level testing. We will always give
you a realistic estimate at drop-off and call you if anything changes. If a
part needs to be specially ordered because we don't stock it for a rarer
model, we will tell you that up front rather than let you wait without
warning, and we can usually get uncommon parts within two business days.

## Drop-off and Pickup

Walk-ins are welcome during business hours, but booking ahead online
guarantees a same-day slot. When you drop off a device, we log its
condition and any existing damage together with you before we start, so
there is never a dispute about what was already there. You can pick up
during business hours; if you need after-hours pickup, ask at drop-off and
we will arrange it. We text you the moment your repair is finished so you
are not left guessing, and devices left unclaimed after 30 days are subject
to a small daily storage fee, waived if you let us know in advance that
you'll be delayed.

## Refunds and Cancellations

If we are unable to complete a repair, you owe nothing and get your device
back as-is. If you change your mind after a repair is finished and picked
up, we offer a full refund within 14 days as long as the part has not been
damaged by misuse. Diagnostic fees are waived if you proceed with the
repair we recommend. Cancelling before we've opened the device is always
free; once a part has been installed, a restocking portion of the price
may apply since the part can no longer be resold as new.
"""

FAQ_MD = """# Frequently Asked Questions

## Do I need an appointment?

No, walk-ins are always welcome. Booking ahead online just guarantees you a
same-day slot during busy periods like weekends.

## What happens to my data during a repair?

We never access personal data, accounts, or photos during a hardware
repair. For software or data-recovery work specifically, we ask you to
sign a separate consent form, and only the technician assigned to your
device has access. We recommend backing up your device before any repair,
though hardware repairs like screens and batteries essentially never touch
your data.

## Do you price match?

Yes. Bring a written quote from another licensed repair shop for the same
part and device, and we will match it as long as the part quality is
equivalent (OEM to OEM, aftermarket to aftermarket).

## What if my phone is still broken after the repair?

Any issue related to the part we replaced is covered by the 90-day
warranty at no extra charge. If it is a different, unrelated issue, we
will diagnose it and give you a new quote before doing any further work.

## Can you repair phones you didn't sell me?

Yes, we repair any brand and model we stock parts for, regardless of where
you bought the phone. We do not require proof of purchase for a repair,
only for warranty claims on repairs we previously performed ourselves.

## Do you offer loaner phones?

We keep a small number of basic loaner phones for customers whose repair
will take more than a day, such as water damage cases. Ask at drop-off -
loaners are first-come, first-served and require a small refundable
deposit.

## Are your technicians certified?

Every technician completes an in-house certification program covering all
the device families we service before working unsupervised, and senior
technicians hold manufacturer-recognized repair certifications where they
exist.
"""

PRICE_LIST_MD = """# Price List

## Screen Repairs

Screen repair pricing depends on device tier. Budget and mid-range Android
phones start at 59 dollars for a screen replacement. Flagship phones like
recent iPhones and Samsung Galaxy models are 129 dollars for a standard
aftermarket screen, or 179 dollars if you want an original OEM display.
Tablets are priced individually since screen sizes vary so much - ask at
drop-off for a quote. Foldable phone screens are handled as a special order
and quoted after we see the device, since parts and labor vary widely
between models.

## Batteries and Charging

A standard battery replacement is 49 dollars for most phones, or 69 dollars
for flagship models with larger batteries. Charging port repair, which
covers a loose or non-functioning charging port, is 45 dollars. If your
phone won't charge at all, we run a free diagnostic first to confirm
whether it's the port or something else before quoting. Wireless charging
coil replacement, needed when a phone stops charging on a pad but still
charges by cable, is 55 dollars.

## Diagnostics and Other Repairs

A general diagnostic fee is 20 dollars, waived if you proceed with the
recommended repair. Water damage assessment and cleaning is 35 dollars,
with further repair quoted separately once we see the extent of the
damage. Camera module replacement is 55 dollars, and speaker or microphone
repair is 40 dollars. Back glass replacement on phones with a glass rear
panel is 65 dollars.

## Rush Service and Accessories

Rush service, which moves your repair to the front of the queue, is a flat
15 dollar add-on on top of the repair price. We also sell phone cases
starting at 15 dollars and tempered-glass screen protectors at 10 dollars,
both with free installation. Replacement charging cables are 12 dollars and
wall adapters are 18 dollars.
"""


async def _wipe_existing(conn: AppConnection, slug: str) -> None:
    existing_id = await conn.fetchval("select id from tenants where slug = $1", slug)
    if existing_id is not None:
        await conn.execute("delete from tenants where id = $1", existing_id)


async def _seed_core(tenant_id: UUID) -> None:
    async with db.tenant_context(None, "service") as conn:
        await conn.execute(
            "insert into tenants (id, slug, name, status) values ($1, $2, $3, 'active')",
            tenant_id,
            SLUG,
            TENANT_NAME,
        )
        await conn.execute(
            "insert into tenant_config (tenant_id, tone, escalation_threshold, brand, config) "
            "values ($1, 'friendly', 0.5, $2, $3)",
            tenant_id,
            json.dumps({"display_name": TENANT_NAME, "accent": "#D97757"}),
            # config->'customer' is the T-032 customer-surface block: the
            # greeting shown as the first assistant bubble and the suggested
            # starter chips on an empty conversation (frontend.md 7.1).
            json.dumps(
                {
                    "customer": {
                        "greeting": (
                            "Hi! Welcome to ByteFix Repairs. I can quote a repair, "
                            "check on an existing ticket, or answer questions about "
                            "our services - what can I do for you?"
                        ),
                        "starter_questions": [
                            "How much is a screen replacement?",
                            "What's the status of my repair?",
                            "How long do repairs usually take?",
                        ],
                    }
                }
            ),
        )

    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        for name, description, price_cents in CATALOG_ITEMS:
            await conn.execute(
                "insert into catalog_items (tenant_id, name, description, price_cents) "
                "values ($1, $2, $3, $4)",
                tenant_id,
                name,
                description,
                price_cents,
            )
        for code, label, unit_amount_cents, unit in PRICING_RULES:
            await conn.execute(
                "insert into pricing_rules (tenant_id, code, label, unit_amount_cents, unit) "
                "values ($1, $2, $3, $4, $5)",
                tenant_id,
                code,
                label,
                unit_amount_cents,
                unit,
            )
        for i in range(15):
            await conn.execute(
                "insert into orders (tenant_id, ref_code, kind, customer_ref, status, details) "
                "values ($1, $2, 'repair', $3, $4, $5)",
                tenant_id,
                f"R-{1001 + i}",
                f"customer-{i + 1}",
                REPAIR_STATUSES[i % len(REPAIR_STATUSES)],
                json.dumps({"device": "phone", "issue": "repair"}),
            )
        for i in range(5):
            await conn.execute(
                "insert into orders (tenant_id, ref_code, kind, customer_ref, status, details) "
                "values ($1, $2, 'order', $3, $4, $5)",
                tenant_id,
                f"ORD-{2001 + i}",
                f"customer-{i + 1}",
                ORDER_STATUSES[i % len(ORDER_STATUSES)],
                json.dumps({"items": ["accessory"]}),
            )


async def _seed_knowledge(tenant_id: UUID, embedder: Embedder) -> None:
    uploads_dir = Path(get_settings().uploads_dir) / str(tenant_id)
    uploads_dir.mkdir(parents=True, exist_ok=True)

    docs = [
        ("policy.md", "policy", POLICY_MD),
        ("faq.md", "faq", FAQ_MD),
        ("price_list.md", "price_list", PRICE_LIST_MD),
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


async def seed(embedder: Embedder | None = None) -> UUID:
    """Seed (or re-seed) Tenant 1. Returns the tenant id."""
    created_pool = False
    try:
        db.get_pool()
    except RuntimeError:
        await db.create_pool()
        created_pool = True

    try:
        async with db.tenant_context(None, "platform_admin") as conn:
            await _wipe_existing(conn, SLUG)

        tenant_id = uuid4()
        await _seed_core(tenant_id)
        print(f"seeded core data for tenant {tenant_id} (slug={SLUG})")

        resolved_embedder = embedder or get_embedder(get_settings())
        await _seed_knowledge(tenant_id, resolved_embedder)
        print("ingested knowledge documents and catalog items")

        return tenant_id
    finally:
        if created_pool:
            await db.close_pool()


def main() -> None:
    tenant_id = asyncio.run(seed())
    print(f"done: tenant_id={tenant_id}")


if __name__ == "__main__":
    main()
