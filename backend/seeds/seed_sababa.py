"""Tenant 3 seed: Sabbaba, a Middle Eastern restaurant (Bondi Junction).

Curated from ``backend/tests/fixtures/sabbaba_profile.txt`` (the W-6
extraction fixture): only flat menu figures become prices. The Plate and
base Pita Pocket share a "$20-$30" range in the source, so they seed with
``price_cents=None`` rather than a number picked out of the range - the
same rule ``test_offering_extraction.py`` pins on the extraction path.
Review-quoted figures ("around $18", "another said the $18 plate") never
become data here.

Idempotent: re-running wipes and recreates tenant 'sababa' from scratch.
Standalone staging use (non-destructive to the other tenants)::

    docker compose run --rm \
      -e DATABASE_URL='<pooler url, port 5432>' \
      backend python -m seeds.seed_sababa

``make seed`` (the full demo world) also calls :func:`seed`, so local dev
gets bytefix + lumident + sababa together.

Usage: ``uv run python -m seeds.seed_sababa``
"""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

from app.llm.embedder import Embedder, get_embedder
from app.shared import db
from app.shared.config import get_settings
from seeds import _helpers

SLUG = "sababa"
TENANT_NAME = "Sabbaba"

# Pre-onboarded profile - the demo world lands in the console, not the
# interview, so the seed writes the same end-state a real confirm produces
# (via _helpers.insert_tenant_core's profile arg). Owner name and headcount
# are demo placeholders; everything else follows the fixture.
SABABA_PROFILE = {
    "owner_display_name": "Noa",
    "business_name": TENANT_NAME,
    "business_type": "Middle Eastern restaurant",
    "headcount": "8",
    "hours": "Monday to Sunday 11am to 8pm",
    "services": ("Pita pockets, bowls, plates, salads and dips, sides, falafel, soft drinks"),
    "contact": "owner@sababa.dev",
    "abn": "none",
    "gst": "no",
    # W-9: the voice beat is part of the interview now, so a pre-onboarded
    # tenant carries the same end-state a real confirm leaves behind.
    "customer_voice_preset": "warm_casual",
    "customer_voice_custom_style": "",
}

# --- offerings: flat menu figures only; ranged items carry no price --------

CATALOG_ITEMS: list[tuple[str, str, int | None, str | None]] = [
    ("Bowl", "Salads and dips with pita on the side", 2700, "Plates & Bowls"),
    (
        "Super Plate",
        "Choice of two proteins, four seasonal salads and two dips",
        3700,
        "Plates & Bowls",
    ),
    (
        "Plate",
        "Salads and dips with one pita, priced $20-$30 depending on build",
        None,
        "Plates & Bowls",
    ),
    (
        "Pita Pocket",
        "Salads and dips wrapped in pita, priced $20-$30 depending on build",
        None,
        "Pitas",
    ),
    (
        "Sabbaba Pita Pocket",
        "House pita with the full four-salad, four-dip combo",
        2000,
        "Pitas",
    ),
    (
        "Larnaca Pita",
        "Olives, green chilli and shredded halloumi",
        1990,
        "Pitas",
    ),
    ("Algerian Pita", "Chickpeas and eggplant", 1990, "Pitas"),
    ("Tunisian Pita", "Marrakech salad and sweet potato", 2000, "Pitas"),
    (
        "Cancun Pita",
        "Salsa, sour cream, guacamole, jalapenos, corn chips and cheese",
        2190,
        "Pitas",
    ),
    ("Hot Chips", "Famous lightly seasoned chips", 1000, "Sides"),
    ("Six Falafel", "Six falafel pieces", 1090, "Sides"),
    ("Soft Drink Can", "A can of soft drink", 450, "Drinks"),
]

# --- pricing_rules: one per flat-priced offering ----------------------------

PRICING_RULES: list[tuple[str, str, int, str]] = [
    ("bowl", "Bowl with pita on the side", 2700, "each"),
    ("super-plate", "Super Plate", 3700, "each"),
    ("pita-sabbaba", "Sabbaba Pita Pocket", 2000, "each"),
    ("pita-larnaca", "Larnaca Pita", 1990, "each"),
    ("pita-algerian", "Algerian Pita", 1990, "each"),
    ("pita-tunisian", "Tunisian Pita", 2000, "each"),
    ("pita-cancun", "Cancun Pita", 2190, "each"),
    ("hot-chips", "Hot Chips", 1000, "each"),
    ("six-falafel", "Six Falafel", 1090, "each"),
    ("soft-drink-can", "Soft Drink Can", 450, "each"),
]

ORDER_STATUSES = ["pending", "in_progress", "ready_for_pickup", "completed", "cancelled"]

MENU_MD = """# Menu

## Plates and Bowls

The Bowl is $27 and comes with pita on the side instead of wrapped in.
The Super Plate is $37, with a choice of two proteins, four seasonal
salads and two dips. The Plate and the base Pita Pocket both run $20-$30
and come with one pita - the exact price depends on the build, so ask at
the counter for a quote on yours.

## Pita Pockets

The house Sabbaba Pita Pocket is $20 with the full four-salad, four-dip
combo. The Larnaca pocket is $19.90 with olives, green chilli and
shredded halloumi. The Algerian pocket is $19.90, built on chickpeas and
eggplant. The Tunisian pocket is $20 with Marrakech salad and sweet
potato. The Cancun pocket is $21.90 with salsa, sour cream, guacamole,
jalapenos, corn chips and cheese.

## Sides and Drinks

Hot Chips are $10, described as famous and lightly seasoned. Six Falafel
is $10.90. Salads are also sold individually, mostly $10-14 - ask what is
fresh today. A can of soft drink is $4.50.
"""

FAQ_MD = """# Frequently Asked Questions

## Where are you?

77 Spring Street, Bondi Junction NSW 2022, in the Eastgate Bondi Junction
shopping centre. If your map shows a slightly different Spring Street
number, it is the same storefront - ask us and we will point you in.

## When are you open?

Expect roughly 11am to 8pm most days. Holiday hours can differ, so check
with us before coming on a public holiday.

## Is the food vegan-friendly?

Yes. Falafel, salads and dips are the core of the menu and the
plant-based options are clearly defined - ask the counter what is fresh
today.

## Do you deliver?

Ordering is through our listed delivery partners. If delivery shows as
unavailable, that usually reflects the browsing location rather than us -
try again from an address near Bondi Junction or call us.
"""


async def _seed_core(tenant_id: UUID) -> None:
    await _helpers.insert_tenant_core(
        tenant_id=tenant_id,
        slug=SLUG,
        name=TENANT_NAME,
        tone="friendly",
        # Third vertical, same code: the restaurant takes the lean column
        # default (search + escalate) like lumident, so enabled_tools stays
        # unwritten here - only bytefix opts into the commerce tools (D-2).
        brand={"display_name": TENANT_NAME, "accent": "#C2410C"},
        config={
            "customer": {
                "greeting": (
                    "Hi! Welcome to Sabbaba. I can walk you through the menu, "
                    "price up a plate or pita, or answer questions about the "
                    "restaurant - what can I get for you?"
                ),
                "starter_questions": [
                    "How much is the Super Plate?",
                    "What comes in the Sabbaba Pita Pocket?",
                    "When are you open?",
                ],
            }
        },
        business_name=TENANT_NAME,
        profile=SABABA_PROFILE,
    )

    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        await _helpers.insert_offerings(conn, tenant_id, CATALOG_ITEMS)
        await _helpers.insert_pricing_rules(conn, tenant_id, PRICING_RULES)
        await _helpers.insert_orders(
            conn,
            tenant_id,
            [
                (
                    f"SAB-{4001 + i}",
                    "order",
                    f"customer-{i + 1}",
                    ORDER_STATUSES[i % len(ORDER_STATUSES)],
                    {"items": ["pita"]},
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
                ("menu.md", "price_list", MENU_MD),
                ("faq.md", "faq", FAQ_MD),
            ],
            embedder,
        )


async def seed(embedder: Embedder | None = None) -> UUID:
    """Seed (or re-seed) the Sabbaba tenant. Returns the tenant id."""
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
