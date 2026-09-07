"""Tenant 1 (anchor) seed: Bytefix Repairs, a phone repair shop.

Not owned by any single phase-1 ticket's file list, but required by T-010's
golden retrieval set (docs/agencx/design/database.md's seeds section fully
specifies this script's contents; see .agents/memory.md's T-010 entry for
why it's created here rather than earlier).

Idempotent: re-running wipes and recreates tenant 'bytefix' from scratch, so
eval runs always start from the same known state rather than accumulating
duplicate rows across reruns.

Usage: ``uv run python -m seeds.seed_tenant1_phoneshop``
"""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

from app.llm.embedder import Embedder, get_embedder
from app.shared import db
from app.shared.config import get_settings
from seeds import _helpers

SLUG = "bytefix"
TENANT_NAME = "Bytefix Repairs"

# The O-1 profile the tenant is pre-onboarded with: the demo world lands in the
# console, not the interview, so the seed writes the same end-state a real
# onboarding confirm produces (via _helpers.insert_tenant_core's profile arg).
BYTEFIX_PROFILE = {
    "owner_display_name": "Alex",
    "business_name": TENANT_NAME,
    "business_type": "phone repair shop",
    "headcount": "4",
    "hours": "Monday to Friday 9am to 6pm, Saturday 10am to 2pm",
    "services": (
        "Phone and laptop repairs, screen replacements, battery replacements, data recovery"
    ),
    "contact": "owner@bytefix.dev",
    "abn": "none",
    "gst": "no",
    # W-9: the voice beat is part of the interview now, so a pre-onboarded
    # tenant carries the same end-state a real confirm leaves behind.
    "customer_voice_preset": "warm_casual",
    "customer_voice_custom_style": "",
}

# --- offerings: phones, accessories, tiered repair services (~15) -----------

CATALOG_ITEMS: list[tuple[str, str, int | None, str | None]] = [
    ("iPhone 11 (Refurbished, 64GB)", "Grade A refurbished, 90-day warranty", 24900, "Phones"),
    ("iPhone 12 (Refurbished, 128GB)", "Grade A refurbished, 90-day warranty", 34900, "Phones"),
    ("Samsung Galaxy S21 (Refurbished)", "Grade A refurbished, 90-day warranty", 29900, "Phones"),
    ("Google Pixel 6 (Refurbished)", "Grade A refurbished, 90-day warranty", 27900, "Phones"),
    ("Phone Case - Universal", "Shock-absorbing case, most models", 1500, "Accessories"),
    ("Tempered Glass Screen Protector", "9H hardness, free installation", 1000, "Accessories"),
    ("USB-C Charging Cable", "1 meter braided cable", 1200, "Accessories"),
    ("Wall Charger Adapter", "20W fast-charging USB-C adapter", 1800, "Accessories"),
    (
        "Screen Repair - Budget/Mid-range Android",
        "Aftermarket display, same-day",
        5900,
        "Repairs",
    ),
    ("Screen Repair - Flagship (Aftermarket)", "Aftermarket display, same-day", 12900, "Repairs"),
    ("Screen Repair - Flagship (OEM)", "Original display, same-day", 17900, "Repairs"),
    ("Battery Replacement - Standard", "Most phone models, same-day", 4900, "Repairs"),
    ("Battery Replacement - Flagship", "Larger-capacity flagship batteries", 6900, "Repairs"),
    ("Charging Port Repair", "Loose or non-functioning charging port", 4500, "Repairs"),
    (
        "Water Damage Diagnostic",
        "Assessment and cleaning, repair quoted separately",
        3500,
        "Repairs",
    ),
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


async def _seed_core(tenant_id: UUID) -> None:
    await _helpers.insert_tenant_core(
        tenant_id=tenant_id,
        slug=SLUG,
        name=TENANT_NAME,
        tone="friendly",
        # D-2: stated, not inherited. Reference tenant 1 is where the
        # commerce tools get demonstrated, so it opts into all of them -
        # the lean column default (search + escalate) would leave the
        # quoting and order-lookup demo with nothing to run. Tenant 2 takes
        # the default and stays lean, which is the I8 proof: two verticals,
        # one codebase, different config.
        brand={"display_name": TENANT_NAME, "accent": "#D97757"},
        # config->'customer' is the T-032 customer-surface block: the
        # greeting shown as the first assistant bubble and the suggested
        # starter chips on an empty conversation (frontend.md 7.1).
        config={
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
        },
        business_name=TENANT_NAME,
        profile=BYTEFIX_PROFILE,
        enabled_tools=[
            "search_knowledge",
            "recommend_items",
            "get_quote_inputs",
            "lookup_order_or_ticket",
            "create_escalation",
        ],
    )

    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        await _helpers.insert_offerings(conn, tenant_id, CATALOG_ITEMS)
        await _helpers.insert_pricing_rules(conn, tenant_id, PRICING_RULES)
        await _helpers.insert_orders(
            conn,
            tenant_id,
            [
                (
                    f"R-{1001 + i}",
                    "repair",
                    f"customer-{i + 1}",
                    REPAIR_STATUSES[i % len(REPAIR_STATUSES)],
                    {"device": "phone", "issue": "repair"},
                )
                for i in range(15)
            ]
            + [
                (
                    f"ORD-{2001 + i}",
                    "order",
                    f"customer-{i + 1}",
                    ORDER_STATUSES[i % len(ORDER_STATUSES)],
                    {"items": ["accessory"]},
                )
                for i in range(5)
            ],
        )


async def _seed_knowledge(tenant_id: UUID, embedder: Embedder) -> None:
    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        await _helpers.ingest_documents(
            conn,
            tenant_id,
            [
                ("policy.md", "policy", POLICY_MD),
                ("faq.md", "faq", FAQ_MD),
                ("price_list.md", "price_list", PRICE_LIST_MD),
            ],
            embedder,
        )


async def seed(embedder: Embedder | None = None) -> UUID:
    """Seed (or re-seed) Tenant 1. Returns the tenant id."""
    async with _helpers.seed_pool():
        async with db.tenant_context(None, "platform_admin") as conn:
            await _helpers.wipe_tenant(conn, SLUG)

        tenant_id = uuid4()
        await _seed_core(tenant_id)
        print(f"seeded core data for tenant {tenant_id} (slug={SLUG})")

        resolved_embedder = embedder or get_embedder(get_settings())
        await _seed_knowledge(tenant_id, resolved_embedder)
        print("ingested knowledge documents and catalog items")

        return tenant_id


def main() -> None:
    tenant_id = asyncio.run(seed())
    print(f"done: tenant_id={tenant_id}")


if __name__ == "__main__":
    main()
