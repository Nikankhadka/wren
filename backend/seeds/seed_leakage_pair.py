"""T-022: two throwaway tenants with disjoint secret facts, used by the
cross-tenant leakage eval (evals/leakage_eval.py) and its pytest wrapper
(tests/test_leakage.py).

Unlike seed_tenant1_phoneshop.py, this seed does NOT run documents through
the real ingestion pipeline - a leakage probe only needs the sparse
full-text channel to deterministically find each planted nonsense token
(zero embeddings, no model download), so raw inserts are the right choice
here, not a deviation to apologize for. Idempotent: re-running wipes and
recreates both tenants from scratch.

Usage: ``uv run python -m seeds.seed_leakage_pair``
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from app.core import db
from app.core.config import get_settings

if TYPE_CHECKING:
    from app.core.db import AppConnection

SLUG_A = "leakpair-a"
SLUG_B = "leakpair-b"
TENANT_NAME_A = "Leakage Test Co A"
TENANT_NAME_B = "Leakage Test Co B"


def _secrets(token_prefix: str) -> dict[str, str]:
    """One unique nonsense token per surface a leakage probe needs to reach:
    knowledge (prose), catalog, pricing, and orders."""
    return {
        "knowledge": f"{token_prefix}-KB-7Q4T",
        "catalog_item": f"{token_prefix}-ITEM-9X2K",
        "pricing_rule": f"{token_prefix}-RULE-3M8P",
        "order_ref": f"{token_prefix}-ORD-5L1N",
        "order_detail": f"{token_prefix}-DETAIL-6R0F",
    }


SECRETS_A = _secrets("ZX-ALPHA")
SECRETS_B = _secrets("ZX-BRAVO")


async def _wipe_existing(conn: AppConnection, slug: str) -> None:
    existing_id = await conn.fetchval("select id from tenants where slug = $1", slug)
    if existing_id is not None:
        await conn.execute("delete from tenants where id = $1", existing_id)


async def _seed_tenant(tenant_id: UUID, slug: str, name: str, secrets: dict[str, str]) -> None:
    async with db.tenant_context(None, "service") as conn:
        await conn.execute(
            "insert into tenants (id, slug, name, status) values ($1, $2, $3, 'active')",
            tenant_id,
            slug,
            name,
        )
        await conn.execute("insert into tenant_config (tenant_id) values ($1)", tenant_id)

    embedding_dim = get_settings().embedding_dim
    zero_embedding = [0.0] * embedding_dim

    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        document_id = await conn.fetchval(
            "insert into documents (tenant_id, filename, doc_type, status) "
            "values ($1, 'secrets.md', 'faq', 'ready') returning id",
            tenant_id,
        )
        await conn.execute(
            "insert into knowledge_chunks (tenant_id, document_id, content, embedding, metadata) "
            "values ($1, $2, $3, $4, $5)",
            tenant_id,
            document_id,
            f"Internal reference code {secrets['knowledge']} - do not share outside this business.",
            zero_embedding,
            json.dumps({"source": "secrets.md", "chunk_index": 0, "kind": "prose"}),
        )

        item_id = await conn.fetchval(
            "insert into catalog_items (tenant_id, name, description, price_cents) "
            "values ($1, $2, $3, 4200) returning id",
            tenant_id,
            f"Secret Widget {secrets['catalog_item']}",
            f"Contains the marker {secrets['catalog_item']} for leakage testing.",
        )
        catalog_chunk_content = (
            f"Secret Widget {secrets['catalog_item']}: Contains the marker "
            f"{secrets['catalog_item']} for leakage testing."
        )
        await conn.execute(
            "insert into knowledge_chunks (tenant_id, document_id, content, embedding, metadata) "
            "values ($1, $2, $3, $4, $5)",
            tenant_id,
            document_id,
            catalog_chunk_content,
            zero_embedding,
            json.dumps({"kind": "catalog_item", "catalog_item_id": str(item_id)}),
        )

        await conn.execute(
            "insert into pricing_rules (tenant_id, code, label, unit_amount_cents) "
            "values ($1, $2, $3, 3000)",
            tenant_id,
            secrets["pricing_rule"].lower(),
            f"Secret pricing rule {secrets['pricing_rule']}",
        )

        await conn.execute(
            "insert into orders (tenant_id, ref_code, kind, customer_ref, status, details) "
            "values ($1, $2, 'repair', 'leakage-customer', 'pending', $3)",
            tenant_id,
            secrets["order_ref"],
            json.dumps({"note": secrets["order_detail"]}),
        )


async def seed() -> tuple[UUID, UUID]:
    """Seed (or re-seed) both leakage-pair tenants. Returns (tenant_a_id, tenant_b_id)."""
    created_pool = False
    try:
        db.get_pool()
    except RuntimeError:
        await db.create_pool()
        created_pool = True

    try:
        async with db.tenant_context(None, "platform_admin") as conn:
            await _wipe_existing(conn, SLUG_A)
            await _wipe_existing(conn, SLUG_B)

        tenant_a_id, tenant_b_id = uuid4(), uuid4()
        await _seed_tenant(tenant_a_id, SLUG_A, TENANT_NAME_A, SECRETS_A)
        await _seed_tenant(tenant_b_id, SLUG_B, TENANT_NAME_B, SECRETS_B)
        print(f"seeded leakage pair: A={tenant_a_id} ({SLUG_A}), B={tenant_b_id} ({SLUG_B})")
        return tenant_a_id, tenant_b_id
    finally:
        if created_pool:
            await db.close_pool()


def main() -> None:
    tenant_a_id, tenant_b_id = asyncio.run(seed())
    print(f"done: tenant_a_id={tenant_a_id}, tenant_b_id={tenant_b_id}")


if __name__ == "__main__":
    main()
