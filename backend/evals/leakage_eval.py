"""T-022: cross-tenant leakage eval against seeds/seed_leakage_pair.py's
two throwaway tenants.

RELEASE CRITERION (docs/phases/phase-2-agents-pricing.md T-022): 100% pass
or red - never skipped, never tolerance-ed. Mirrors evals/retrieval_eval.py's
shape (pure metric helper, DB-backed run, eval_runs write, --gate CLI), but
the "metric" here is a pass rate over structural leakage probes, not a
quality score.

Each probe queries a tool/service AS one tenant, FOR the OTHER tenant's
secret, and asserts the victim's secret never appears - the negative
assertion this ticket is about. Each probe also has a positive control (the
same mechanism, queried for the ATTACKER's own secret) so a probe that finds
nothing at all can't trivially "pass" a leakage check that never had teeth.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from starlette.concurrency import run_in_threadpool

from app.agents.tools import lookup_order_or_ticket
from app.core import db
from app.core.config import get_settings
from app.llm.embedder import Embedder
from app.retrieval.rerank import Reranker
from app.retrieval.service import retrieve
from seeds.seed_leakage_pair import SECRETS_A, SECRETS_B, seed


class _ZeroEmbedder(Embedder):
    """CLI-mode embedder double - content-blind but dimensionally correct,
    same role as tests/fakes.py's ZeroEmbedder (not imported from there:
    eval scripts must not depend on the test suite). The sparse/FTS channel
    alone is sufficient to exercise every planted secret, so this eval never
    needs a real embedding model or API call to run."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        dim = get_settings().embedding_dim
        return [[0.0] * dim for _ in texts]


@dataclass(frozen=True)
class CheckResult:
    name: str
    direction: str  # "a_probes_b" | "b_probes_a"
    passed: bool
    detail: str = ""


def find_secret_occurrences(text: str, secrets: Iterable[str]) -> list[str]:
    """Every secret string that appears as a substring of ``text``."""
    return [secret for secret in secrets if secret in text]


def metrics_from(results: list[CheckResult]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    return {
        "pass_count": passed,
        "total": total,
        "pass_rate": (passed / total) if total else 0.0,
        "failures": [r.name for r in results if not r.passed],
    }


class _PassthroughReranker(Reranker):
    async def rerank(self, *, query: str, candidates: list[Any], top_k: int) -> list[Any]:
        return candidates[:top_k]


async def _check_retrieval(
    conn: Any,
    *,
    attacker_id: UUID,
    attacker_label: str,
    victim_label: str,
    victim_secrets: dict[str, str],
    own_secrets: dict[str, str],
    embedder: Embedder,
    reranker: Reranker,
    direction: str,
) -> list[CheckResult]:
    results: list[CheckResult] = []

    for surface, metadata_kind in (("knowledge", None), ("catalog_item", "catalog_item")):
        victim_secret = victim_secrets[surface]
        own_secret = own_secrets[surface]

        victim_chunks = await retrieve(
            conn,
            tenant_id=attacker_id,
            query=victim_secret,
            embedder=embedder,
            reranker=reranker,
            top_k=10,
            metadata_kind=metadata_kind,
        )
        leaked = [
            occurrence
            for chunk in victim_chunks
            for occurrence in find_secret_occurrences(chunk.content, [victim_secret])
        ]
        results.append(
            CheckResult(
                name=f"retrieve({surface}) as {attacker_label} querying {victim_label}'s secret",
                direction=direction,
                passed=not leaked,
                detail=f"leaked: {leaked}" if leaked else "",
            )
        )

        own_chunks = await retrieve(
            conn,
            tenant_id=attacker_id,
            query=own_secret,
            embedder=embedder,
            reranker=reranker,
            top_k=10,
            metadata_kind=metadata_kind,
        )
        found_own = any(own_secret in chunk.content for chunk in own_chunks)
        results.append(
            CheckResult(
                name=f"retrieve({surface}) positive control - {attacker_label} finds own secret",
                direction=direction,
                passed=found_own,
                detail="" if found_own else "own secret not found - probe has no teeth",
            )
        )

    return results


async def _check_order_lookup(
    conn: Any,
    *,
    attacker_id: UUID,
    attacker_label: str,
    victim_label: str,
    victim_secrets: dict[str, str],
    own_secrets: dict[str, str],
    direction: str,
) -> list[CheckResult]:
    results: list[CheckResult] = []

    victim_lookup = await lookup_order_or_ticket(conn, attacker_id, victim_secrets["order_ref"])
    results.append(
        CheckResult(
            name=f"lookup_order_or_ticket as {attacker_label} for {victim_label}'s ref_code",
            direction=direction,
            passed=not victim_lookup.found,
            detail="found victim's order!" if victim_lookup.found else "",
        )
    )

    own_lookup = await lookup_order_or_ticket(conn, attacker_id, own_secrets["order_ref"])
    results.append(
        CheckResult(
            name=f"lookup_order_or_ticket positive control - {attacker_label} finds own order",
            direction=direction,
            passed=own_lookup.found,
            detail="" if own_lookup.found else "own order not found - probe has no teeth",
        )
    )
    return results


async def _check_direct_tables(
    conn: Any,
    *,
    attacker_label: str,
    victim_label: str,
    victim_secrets: dict[str, str],
    own_secrets: dict[str, str],
    direction: str,
) -> list[CheckResult]:
    """Deliberately NO app-side ``tenant_id`` predicate here, unlike every real
    app query (dense/sparse/lookup all carry one - and the retrieval/order
    probes above already prove those paths). These direct reads leave scoping
    entirely to RLS under the attacker's ``tenant_context``, so they are the
    checks that go red if a tenant_isolation policy is ever weakened (the
    T-022 accept criterion). Adding the predicate back would make the negative
    assertion vacuously true regardless of RLS - a probe with no teeth."""
    results: list[CheckResult] = []

    checks = (
        ("pricing_rules", "label", victim_secrets["pricing_rule"], own_secrets["pricing_rule"]),
        ("catalog_items", "name", victim_secrets["catalog_item"], own_secrets["catalog_item"]),
        ("orders", "details::text", victim_secrets["order_detail"], own_secrets["order_detail"]),
    )
    for table, column, victim_secret, own_secret in checks:
        victim_rows = await conn.fetch(
            f"select 1 from {table} where {column} ilike $1",  # noqa: S608
            f"%{victim_secret}%",
        )
        results.append(
            CheckResult(
                name=f"select {table} as {attacker_label} for {victim_label}'s secret",
                direction=direction,
                passed=len(victim_rows) == 0,
                detail=f"found {len(victim_rows)} row(s)" if victim_rows else "",
            )
        )
        own_rows = await conn.fetch(
            f"select 1 from {table} where {column} ilike $1",  # noqa: S608
            f"%{own_secret}%",
        )
        results.append(
            CheckResult(
                name=f"select {table} positive control - {attacker_label} finds own secret",
                direction=direction,
                passed=len(own_rows) > 0,
                detail="" if own_rows else "own row not found - probe has no teeth",
            )
        )
    return results


async def run_db_checks(
    *,
    tenant_a_id: UUID,
    tenant_b_id: UUID,
    embedder: Embedder,
    reranker: Reranker,
) -> list[CheckResult]:
    """Structural leakage checks: retrieval, order lookup, and direct table
    reads, run under each tenant's real RLS context, in both directions."""
    results: list[CheckResult] = []

    async with db.tenant_context(tenant_a_id, "customer") as conn:
        results += await _check_retrieval(
            conn,
            attacker_id=tenant_a_id,
            attacker_label="A",
            victim_label="B",
            victim_secrets=SECRETS_B,
            own_secrets=SECRETS_A,
            embedder=embedder,
            reranker=reranker,
            direction="a_probes_b",
        )
        results += await _check_order_lookup(
            conn,
            attacker_id=tenant_a_id,
            attacker_label="A",
            victim_label="B",
            victim_secrets=SECRETS_B,
            own_secrets=SECRETS_A,
            direction="a_probes_b",
        )
        results += await _check_direct_tables(
            conn,
            attacker_label="A",
            victim_label="B",
            victim_secrets=SECRETS_B,
            own_secrets=SECRETS_A,
            direction="a_probes_b",
        )

    async with db.tenant_context(tenant_b_id, "customer") as conn:
        results += await _check_retrieval(
            conn,
            attacker_id=tenant_b_id,
            attacker_label="B",
            victim_label="A",
            victim_secrets=SECRETS_A,
            own_secrets=SECRETS_B,
            embedder=embedder,
            reranker=reranker,
            direction="b_probes_a",
        )
        results += await _check_order_lookup(
            conn,
            attacker_id=tenant_b_id,
            attacker_label="B",
            victim_label="A",
            victim_secrets=SECRETS_A,
            own_secrets=SECRETS_B,
            direction="b_probes_a",
        )
        results += await _check_direct_tables(
            conn,
            attacker_label="B",
            victim_label="A",
            victim_secrets=SECRETS_A,
            own_secrets=SECRETS_B,
            direction="b_probes_a",
        )

    return results


def _git_sha() -> str:
    result = subprocess.run(  # noqa: S603 - fixed args, no shell, dev-tool only
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False
    )
    return result.stdout.strip()


async def _write_eval_run(conn: Any, tenant_id: UUID, metrics: dict[str, Any]) -> None:
    git_sha = await run_in_threadpool(_git_sha)
    await conn.execute(
        "insert into eval_runs (tenant_id, run_type, metrics, git_sha) "
        "values ($1, 'leakage', $2, $3)",
        tenant_id,
        json.dumps(metrics),
        git_sha,
    )


def _print_table(metrics: dict[str, Any]) -> None:
    print(f"pass_count: {metrics['pass_count']}/{metrics['total']}")
    print(f"pass_rate:  {metrics['pass_rate']:.3f}")
    if metrics["failures"]:
        print("failures:")
        for name in metrics["failures"]:
            print(f"  - {name}")


async def main_async(*, gate: bool) -> int:
    created_pool = False
    try:
        db.get_pool()
    except RuntimeError:
        await db.create_pool()
        created_pool = True

    try:
        tenant_a_id, tenant_b_id = await seed()

        results = await run_db_checks(
            tenant_a_id=tenant_a_id,
            tenant_b_id=tenant_b_id,
            embedder=_ZeroEmbedder(),
            reranker=_PassthroughReranker(),
        )
        metrics_a = metrics_from([r for r in results if r.direction == "a_probes_b"])
        metrics_b = metrics_from([r for r in results if r.direction == "b_probes_a"])

        async with db.tenant_context(tenant_a_id, "tenant_admin") as conn:
            await _write_eval_run(conn, tenant_a_id, metrics_a)
        async with db.tenant_context(tenant_b_id, "tenant_admin") as conn:
            await _write_eval_run(conn, tenant_b_id, metrics_b)

        print("=== A probes B ===")
        _print_table(metrics_a)
        print("=== B probes A ===")
        _print_table(metrics_b)

        overall_pass = metrics_a["pass_rate"] == 1.0 and metrics_b["pass_rate"] == 1.0
        if gate and not overall_pass:
            print("GATE FAILED: leakage check did not reach 100%")
            return 1
        return 0
    finally:
        if created_pool:
            await db.close_pool()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate", action="store_true", help="exit non-zero if pass_rate < 1.0")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main_async(gate=args.gate)))


if __name__ == "__main__":
    main()
