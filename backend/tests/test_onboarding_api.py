"""T-006: onboarding endpoints exercised at the API level, LLM provider stubbed.

Same client-fixture pattern as test_auth_api.py, plus a FastAPI dependency
override so `/message` never calls a real model - `FakeProvider` (mirrors
test_onboarding_flow.py's) returns canned drafts keyed by schema.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import asyncpg
import httpx
import jwt
import pytest
import pytest_asyncio
from pydantic import BaseModel

from app.core import db
from app.core.config import get_settings
from app.llm.dependency import get_embedder_dependency, get_llm_provider
from app.llm.provider import SchemaT
from app.main import app
from app.onboarding.flow import (
    EscalationDraft,
    IdentityDraft,
    PricingRulesDraft,
    ServicesDraft,
    ToneDraft,
)
from tests.conftest import _app_dsn_for
from tests.fakes import BaseFakeProvider, ZeroEmbedder

pytestmark = pytest.mark.db

TEST_JWT_SECRET = "test-only-supabase-jwt-secret-do-not-use-in-prod"  # noqa: S105


class FakeProvider(BaseFakeProvider):
    def __init__(self, responses: dict[type[BaseModel], BaseModel]) -> None:
        self._responses = responses

    async def extract(
        self, *, system_prompt: str, user_input: str, schema: type[SchemaT]
    ) -> SchemaT:
        return self._responses[schema]  # type: ignore[return-value]


FAKE_RESPONSES: dict[type[BaseModel], BaseModel] = {
    IdentityDraft: IdentityDraft(description="A neighborhood phone repair shop."),
    ToneDraft: ToneDraft(tone="friendly"),
    ServicesDraft: ServicesDraft.model_validate(
        {
            "items": [
                {"name": "Screen repair", "description": "Cracked screens", "price_dollars": 89.5}
            ]
        }
    ),
    PricingRulesDraft: PricingRulesDraft.model_validate(
        {
            "rules": [
                {
                    "code": "rush-fee",
                    "label": "Rush service",
                    "unit_amount_dollars": 25.0,
                    "unit": "flat",
                }
            ]
        }
    ),
    EscalationDraft: EscalationDraft(threshold=0.6),
}


@pytest.fixture(autouse=True)
def _supabase_jwt_secret_env() -> Iterator[None]:
    import os

    original = os.environ.get("SUPABASE_JWT_SECRET")
    os.environ["SUPABASE_JWT_SECRET"] = TEST_JWT_SECRET
    get_settings.cache_clear()
    yield
    if original is None:
        os.environ.pop("SUPABASE_JWT_SECRET", None)
    else:
        os.environ["SUPABASE_JWT_SECRET"] = original
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def client(migrated_db: str) -> AsyncIterator[httpx.AsyncClient]:
    await db.create_pool(dsn=_app_dsn_for(migrated_db), min_size=1, max_size=4)
    app.dependency_overrides[get_llm_provider] = lambda: FakeProvider(FAKE_RESPONSES)
    app.dependency_overrides[get_embedder_dependency] = ZeroEmbedder
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)
        app.dependency_overrides.pop(get_embedder_dependency, None)
        await db.close_pool()


def _make_token(user_id: uuid.UUID) -> str:
    now = int(time.time())
    payload = {"sub": str(user_id), "aud": "authenticated", "iat": now, "exp": now + 3600}
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")


async def _signup_tenant_admin(client: httpx.AsyncClient) -> tuple[str, uuid.UUID]:
    user_id = uuid.uuid4()
    token = _make_token(user_id)
    slug = f"onboard-{uuid.uuid4().hex[:8]}"
    response = await client.post(
        "/api/tenants",
        json={"slug": slug, "name": "Onboarding Test Co"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    return token, uuid.UUID(response.json()["tenant_id"])


async def _walk_to_confirm(client: httpx.AsyncClient, token: str) -> None:
    headers = {"Authorization": f"Bearer {token}"}
    replies = [
        "we fix phones",
        "keep it friendly",
        "screen repairs for $89.50",
        "rush fee is $25",
        "escalate when unsure",
        "ready",
    ]
    for reply in replies:
        response = await client.post(
            "/api/onboarding/message", json={"text": reply}, headers=headers
        )
        assert response.status_code == 200, response.text


async def test_fresh_tenant_starts_at_identity(client: httpx.AsyncClient) -> None:
    token, _tenant_id = await _signup_tenant_admin(client)
    response = await client.get(
        "/api/onboarding/state", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["stage"] == "identity"
    assert body["completed"] is False
    assert body["draft"] == {}


async def test_message_advances_stage_and_persists_draft(client: httpx.AsyncClient) -> None:
    token, _tenant_id = await _signup_tenant_admin(client)
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.post(
        "/api/onboarding/message", json={"text": "we fix phones"}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["stage"] == "tone"
    description = response.json()["draft"]["identity"]["description"]
    assert description == "A neighborhood phone repair shop."

    # A fresh GET (simulating a page refresh) resumes from the persisted stage.
    resumed = await client.get("/api/onboarding/state", headers=headers)
    assert resumed.json()["stage"] == "tone"


async def test_full_flow_confirm_writes_tenant_config_and_catalog(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    token, tenant_id = await _signup_tenant_admin(client)
    headers = {"Authorization": f"Bearer {token}"}
    await _walk_to_confirm(client, token)

    state = await client.get("/api/onboarding/state", headers=headers)
    assert state.json()["stage"] == "confirm"

    confirm = await client.post("/api/onboarding/confirm", headers=headers)
    assert confirm.status_code == 200
    body = confirm.json()
    assert body["catalog_items_created"] == 1
    assert body["pricing_rules_created"] == 1

    config_row = await superuser_conn.fetchrow(
        "select system_prompt, tone, escalation_threshold from tenant_config where tenant_id = $1",
        tenant_id,
    )
    assert config_row is not None
    assert "phone repair shop" in config_row["system_prompt"]
    assert config_row["tone"] == "friendly"
    assert config_row["escalation_threshold"] == pytest.approx(0.6)

    item_row = await superuser_conn.fetchrow(
        "select name, price_cents from catalog_items where tenant_id = $1", tenant_id
    )
    assert item_row is not None
    assert item_row["name"] == "Screen repair"
    assert item_row["price_cents"] == 8950

    rule_row = await superuser_conn.fetchrow(
        "select code, unit_amount_cents from pricing_rules where tenant_id = $1", tenant_id
    )
    assert rule_row is not None
    assert rule_row["code"] == "rush-fee"
    assert rule_row["unit_amount_cents"] == 2500

    # T-008: confirm also ingests catalog_items into a synthetic 'catalog'
    # document, proving the ingest_catalog_items wiring rather than letting a
    # provider failure silently mark it failed.
    catalog_doc = await superuser_conn.fetchrow(
        "select id, status from documents where tenant_id = $1 and doc_type = 'catalog'",
        tenant_id,
    )
    assert catalog_doc is not None
    assert catalog_doc["status"] == "ready"
    chunk_row = await superuser_conn.fetchrow(
        "select content, metadata from knowledge_chunks where document_id = $1",
        catalog_doc["id"],
    )
    assert chunk_row is not None
    assert "Screen repair" in chunk_row["content"]


async def test_confirm_before_final_stage_is_conflict(client: httpx.AsyncClient) -> None:
    token, _tenant_id = await _signup_tenant_admin(client)
    response = await client.post(
        "/api/onboarding/confirm", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 409


async def test_double_confirm_is_conflict(client: httpx.AsyncClient) -> None:
    token, _tenant_id = await _signup_tenant_admin(client)
    headers = {"Authorization": f"Bearer {token}"}
    await _walk_to_confirm(client, token)

    first = await client.post("/api/onboarding/confirm", headers=headers)
    assert first.status_code == 200
    second = await client.post("/api/onboarding/confirm", headers=headers)
    assert second.status_code == 409


async def test_message_at_confirm_stage_is_conflict(client: httpx.AsyncClient) -> None:
    token, _tenant_id = await _signup_tenant_admin(client)
    headers = {"Authorization": f"Bearer {token}"}
    await _walk_to_confirm(client, token)

    response = await client.post(
        "/api/onboarding/message", json={"text": "anything"}, headers=headers
    )
    assert response.status_code == 409
