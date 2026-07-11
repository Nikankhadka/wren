"""T-010: golden retrieval eval against Tenant 1's seeded knowledge.

Loads evals/datasets/tenant1_retrieval.jsonl into eval_cases (idempotent -
wipes and reinserts this tenant's 'retrieval' cases each run), runs
service.retrieve() per case, computes recall@3, recall@5, MRR, and nDCG@5,
writes an eval_runs row, and prints a table. Negative (out-of-domain) cases
are reported separately (mean top-1 rerank score) rather than folded into
recall/MRR/nDCG, which are only meaningful when there's an actual relevant
chunk to find.

Usage: ``uv run python -m evals.retrieval_eval [--gate] [--top-k 5]``
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

from starlette.concurrency import run_in_threadpool

from app.core import config, db
from app.llm.embedder import get_embedder
from app.retrieval.rerank import get_reranker
from app.retrieval.service import retrieve
from seeds.seed_tenant1_phoneshop import SLUG

if TYPE_CHECKING:
    from app.llm.embedder import Embedder
    from app.retrieval.rerank import Reranker
    from app.retrieval.types import RetrievedChunk

DATASET_PATH = Path(__file__).parent / "datasets" / "tenant1_retrieval.jsonl"
RECALL_AT_5_GATE = 0.85


@dataclass(frozen=True)
class EvalCase:
    query: str
    expected_chunks: list[dict[str, Any]]
    negative: bool = False


def load_cases(path: Path = DATASET_PATH) -> list[EvalCase]:
    cases = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        raw = json.loads(line)
        cases.append(
            EvalCase(
                query=raw["query"],
                expected_chunks=raw["expected_chunks"],
                negative=raw.get("negative", False),
            )
        )
    return cases


def is_relevant(chunk: RetrievedChunk, expected: dict[str, Any]) -> bool:
    if "catalog_item_name" in expected:
        return chunk.metadata.get("kind") == "catalog_item" and chunk.content.startswith(
            expected["catalog_item_name"]
        )
    if "source" in expected:
        return bool(
            chunk.metadata.get("source") == expected["source"]
            and chunk.metadata.get("chunk_index") == expected["chunk_index"]
        )
    return False


def first_relevant_rank(
    results: list[RetrievedChunk], expected_chunks: list[dict[str, Any]]
) -> int | None:
    """1-indexed rank of the first result matching any of ``expected_chunks``, or
    None if none of the returned results match."""
    for rank, chunk in enumerate(results, start=1):
        if any(is_relevant(chunk, expected) for expected in expected_chunks):
            return rank
    return None


# --- pure metric functions (unit-tested with known-answer fixtures) --------------


def recall_at_k(ranks: list[int | None], k: int) -> float:
    if not ranks:
        return 0.0
    hits = sum(1 for rank in ranks if rank is not None and rank <= k)
    return hits / len(ranks)


def mrr(ranks: list[int | None]) -> float:
    if not ranks:
        return 0.0
    return sum(1.0 / rank if rank is not None else 0.0 for rank in ranks) / len(ranks)


def ndcg_at_k(ranks: list[int | None], k: int) -> float:
    """nDCG@k for single-relevant-item cases: DCG is 1/log2(rank+1) if the
    relevant item is within the top k, IDCG is always 1/log2(2) = 1 (the
    ideal case places it at rank 1), so nDCG@k simplifies to DCG@k."""
    if not ranks:
        return 0.0
    total = sum(
        1.0 / math.log2(rank + 1) if rank is not None and rank <= k else 0.0 for rank in ranks
    )
    return total / len(ranks)


# --- DB-backed evaluation run -----------------------------------------------------


async def _sync_eval_cases(conn: Any, tenant_id: UUID, cases: list[EvalCase]) -> None:
    await conn.execute(
        "delete from eval_cases where tenant_id = $1 and case_type = 'retrieval'", tenant_id
    )
    for case in cases:
        await conn.execute(
            "insert into eval_cases (tenant_id, case_type, input, expected) "
            "values ($1, 'retrieval', $2, $3)",
            tenant_id,
            json.dumps({"query": case.query}),
            json.dumps({"expected_chunks": case.expected_chunks, "negative": case.negative}),
        )


async def run_eval(
    conn: Any,
    *,
    tenant_id: UUID,
    cases: list[EvalCase],
    embedder: Embedder,
    reranker: Reranker,
    top_k: int = 5,
) -> dict[str, float]:
    await _sync_eval_cases(conn, tenant_id, cases)

    positive_ranks: list[int | None] = []
    negative_top_scores: list[float] = []

    for case in cases:
        results = await retrieve(
            conn,
            tenant_id=tenant_id,
            query=case.query,
            embedder=embedder,
            reranker=reranker,
            top_k=top_k,
        )
        if case.negative:
            negative_top_scores.append(results[0].score if results else 0.0)
        else:
            positive_ranks.append(first_relevant_rank(results, case.expected_chunks))

    metrics = {
        "recall_at_3": recall_at_k(positive_ranks, 3),
        "recall_at_5": recall_at_k(positive_ranks, 5),
        "mrr": mrr(positive_ranks),
        "ndcg_at_5": ndcg_at_k(positive_ranks, 5),
        "positive_cases": float(len(positive_ranks)),
        "negative_cases": float(len(negative_top_scores)),
    }
    if negative_top_scores:
        metrics["negative_avg_top_score"] = sum(negative_top_scores) / len(negative_top_scores)
    return metrics


def _git_sha() -> str:
    result = subprocess.run(  # noqa: S603 - fixed args, no shell, dev-tool only
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False
    )
    return result.stdout.strip()


async def _write_eval_run(conn: Any, tenant_id: UUID, metrics: dict[str, float]) -> None:
    git_sha = await run_in_threadpool(_git_sha)
    await conn.execute(
        "insert into eval_runs (tenant_id, run_type, metrics, git_sha) "
        "values ($1, 'retrieval', $2, $3)",
        tenant_id,
        json.dumps(metrics),
        git_sha,
    )


def _print_table(metrics: dict[str, float]) -> None:
    print(f"{'metric':<24}{'value'}")
    print("-" * 36)
    for key, value in metrics.items():
        print(f"{key:<24}{value:.3f}" if isinstance(value, float) else f"{key:<24}{value}")


async def main_async(*, gate: bool, top_k: int) -> int:
    created_pool = False
    try:
        db.get_pool()
    except RuntimeError:
        await db.create_pool()
        created_pool = True

    try:
        async with db.tenant_context(None, "platform_admin") as conn:
            tenant_id = await conn.fetchval("select id from tenants where slug = $1", SLUG)
        if tenant_id is None:
            print(f"tenant '{SLUG}' not seeded - run seeds.seed_tenant1_phoneshop first")
            return 1

        settings = config.get_settings()
        embedder = get_embedder(settings)
        reranker = get_reranker(settings)
        cases = load_cases()

        async with db.tenant_context(tenant_id, "tenant_admin") as conn:
            metrics = await run_eval(
                conn,
                tenant_id=tenant_id,
                cases=cases,
                embedder=embedder,
                reranker=reranker,
                top_k=top_k,
            )
            await _write_eval_run(conn, tenant_id, metrics)

        _print_table(metrics)

        if gate and metrics["recall_at_5"] < RECALL_AT_5_GATE:
            print(f"GATE FAILED: recall_at_5 {metrics['recall_at_5']:.3f} < {RECALL_AT_5_GATE}")
            return 1
        return 0
    finally:
        if created_pool:
            await db.close_pool()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gate", action="store_true", help=f"exit non-zero if recall@5 < {RECALL_AT_5_GATE}"
    )
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main_async(gate=args.gate, top_k=args.top_k)))


if __name__ == "__main__":
    main()
