"""The hosted embedder's schema contract (B-4).

The production image ships without sentence-transformers, so the deployed stack
runs EMBEDDER=google. That makes an external service responsible for a value the
database constrains: knowledge_chunks.embedding is vector(384) (migration 0010),
and gemini-embedding-001 is natively 3072. The width therefore depends on the API
honouring outputDimensionality, which is exactly the kind of thing that fails
silently after a provider-side change - and did: the batch endpoint ignores the
field when it is nested under embedContentConfig, so every ingest failed with a
3072-dim guard error until the request moved it to the top level. These tests pin
the contract: the right implementation is selected by env, the request carries
the dimension at the level the API honours, a wrong width is refused with an
actionable message rather than surfacing as a Postgres type error at insert time,
and truncated vectors come back normalized.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable

import httpx
import pytest

from app.llm.embedder import AzureOpenAIEmbedder, GoogleEmbedder, LocalEmbedder, get_embedder
from app.shared.config import Settings


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "embedder": "google",
        "llm_api_key": "test-key",
        "google_embed_model": "gemini-embedding-001",
        "embedding_dim": 384,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def _stub(
    embedder: GoogleEmbedder, handler: Callable[[httpx.Request], httpx.Response]
) -> list[httpx.Request]:
    """Point the embedder at an in-process transport, capturing what it sends."""
    seen: list[httpx.Request] = []

    def _capture(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    embedder._client = httpx.AsyncClient(transport=httpx.MockTransport(_capture))
    return seen


def test_get_embedder_selects_google_by_env() -> None:
    assert isinstance(get_embedder(_settings()), GoogleEmbedder)


def test_get_embedder_still_honours_the_other_backends() -> None:
    azure = _settings(
        embedder="azure",
        # AsyncAzureOpenAI refuses to construct without an endpoint and a key,
        # so selection cannot be asserted without them.
        azure_openai_endpoint="https://example.openai.azure.com",
        azure_openai_api_key="test-key",
    )
    assert isinstance(get_embedder(azure), AzureOpenAIEmbedder)
    assert isinstance(get_embedder(_settings(embedder="local")), LocalEmbedder)
    # An unknown value falls back to local rather than failing closed - the
    # pre-existing behaviour, pinned so adding 'google' did not change it.
    assert isinstance(get_embedder(_settings(embedder="nonsense")), LocalEmbedder)


async def test_embed_requests_the_schema_dimension_and_normalizes() -> None:
    embedder = GoogleEmbedder(_settings())
    # A deliberately un-normalized vector: the API returns raw truncated values.
    raw = [3.0, 4.0] + [0.0] * 382

    seen = _stub(
        embedder,
        lambda _r: httpx.Response(200, json={"embeddings": [{"values": raw}]}),
    )
    vectors = await embedder.embed(["hello"])

    body = json.loads(seen[0].content)
    assert seen[0].headers["x-goog-api-key"] == "test-key"
    assert "gemini-embedding-001:batchEmbedContents" in str(seen[0].url)
    # Top-level: the API ignores the nested embedContentConfig form.
    assert body["requests"][0]["outputDimensionality"] == 384
    assert "embedContentConfig" not in body["requests"][0]
    assert body["requests"][0]["content"]["parts"] == [{"text": "hello"}]

    assert len(vectors[0]) == 384
    assert math.isclose(math.sqrt(sum(v * v for v in vectors[0])), 1.0, rel_tol=1e-9)
    # Direction preserved: 3/5 and 4/5.
    assert math.isclose(vectors[0][0], 0.6, rel_tol=1e-9)
    assert math.isclose(vectors[0][1], 0.8, rel_tol=1e-9)


async def test_embed_preserves_input_order() -> None:
    embedder = GoogleEmbedder(_settings())
    first = [1.0] + [0.0] * 383
    second = [0.0, 1.0] + [0.0] * 382
    _stub(
        embedder,
        lambda _r: httpx.Response(
            200, json={"embeddings": [{"values": first}, {"values": second}]}
        ),
    )

    vectors = await embedder.embed(["a", "b"])

    assert vectors[0][0] == 1.0
    assert vectors[1][1] == 1.0


async def test_embed_refuses_a_width_the_schema_cannot_hold() -> None:
    """The failure this exists for: the endpoint ignores outputDimensionality and
    hands back the model's native 3072."""
    embedder = GoogleEmbedder(_settings())
    _stub(
        embedder,
        lambda _r: httpx.Response(200, json={"embeddings": [{"values": [0.1] * 3072}]}),
    )

    with pytest.raises(ValueError, match="3072-dim"):
        await embedder.embed(["hello"])


async def test_embed_short_circuits_on_empty_input() -> None:
    embedder = GoogleEmbedder(_settings())
    seen = _stub(embedder, lambda _r: httpx.Response(500))

    assert await embedder.embed([]) == []
    assert seen == []


async def test_embed_raises_on_api_error() -> None:
    embedder = GoogleEmbedder(_settings())
    _stub(embedder, lambda _r: httpx.Response(429, json={"error": "rate limited"}))

    with pytest.raises(httpx.HTTPStatusError):
        await embedder.embed(["hello"])


def test_zero_vector_survives_normalization() -> None:
    """Guards the division in _normalize: a degenerate all-zero embedding must
    come back as-is rather than as NaNs the index would silently accept."""
    embedder = GoogleEmbedder(_settings())
    _stub(embedder, lambda _r: httpx.Response(200, json={"embeddings": []}))

    from app.llm.embedder import _normalize

    assert _normalize([0.0] * 384) == [0.0] * 384
