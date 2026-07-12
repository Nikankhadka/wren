"""T-023: generation eval against Tenant 1's seeded knowledge, driven
through the real Knowledge path (build_graph(), forced to route="knowledge"
- get_runtime() only works inside an actual node execution, see T-013's
memory entry, so knowledge.run() is never called directly).

RAGAS-equivalent metrics, not the ``ragas`` package: this codebase
deliberately avoids LangChain chat-model wrappers everywhere (T-012), and
real ragas metrics are built around exactly that. Faithfulness and answer
relevancy are implemented here as plain LLM-judged checks through this
project's own ``LLMProvider.extract()`` - the same structured-output
pattern already used by app/agents/inspection.py's grounding check and
app/pricing/validation_gate.py - at a fraction of the dependency weight.

Citation-faithfulness is this ticket's own addition, distinct from RAGAS's
answer-level faithfulness: for each cited sentence in the draft, does the
SPECIFIC chunk cited at that bracket index actually support THAT sentence
(not just the answer as a whole)?

Unlike evals/leakage_eval.py, this eval requires a real LLM provider - it
is a quality measurement, not a structural security proof, so it is not
CI-deterministic by nature and is not the never-skipped release criterion
T-022 is. Score whatever the customer would actually see: the graph runs
Inspection (T-021) too, so a case's final draft may already be a redraft
or an escalation handoff, not just the Knowledge node's first attempt.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.agents.escalation import HANDOFF_MESSAGE
from app.agents.graph import build_graph
from app.agents.inspection import ESCALATION_MESSAGE
from app.agents.knowledge import REFUSAL_MESSAGE
from app.agents.state import AgentState, GraphContext
from app.core import config, db
from app.llm.dependency import get_llm_provider
from app.llm.embedder import Embedder, get_embedder
from app.llm.provider import LLMProvider
from app.retrieval.rerank import Reranker, get_reranker
from seeds.seed_tenant1_phoneshop import SLUG

DATASET_PATH = Path(__file__).parent / "datasets" / "tenant1_generation.jsonl"
FAITHFULNESS_GATE = 0.85
RELEVANCY_GATE = 0.85
_CITATION_RE = re.compile(r"\[(\d+)\]")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
# Deterministic non-answers the graph can hand back instead of a real draft:
# knowledge's refusal, inspection's second-failure escalation, and the
# escalation node's own handoff. None of these contain verifiable claims or
# citations, so scoring them down the normal path would grade them ~1.0.
_NON_ANSWER_MESSAGES = frozenset({REFUSAL_MESSAGE, ESCALATION_MESSAGE, HANDOFF_MESSAGE})


@dataclass(frozen=True)
class GenerationCase:
    question: str
    reference_facts: list[str] = field(default_factory=list)
    expected_sources: list[str] = field(default_factory=list)
    negative: bool = False


def load_cases(path: Path = DATASET_PATH) -> list[GenerationCase]:
    cases = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        raw = json.loads(line)
        cases.append(
            GenerationCase(
                question=raw["question"],
                reference_facts=raw.get("reference_facts", []),
                expected_sources=raw.get("expected_sources", []),
                negative=raw.get("negative", False),
            )
        )
    return cases


# --- LLM-judged schemas -------------------------------------------------------


class ExtractedClaims(BaseModel):
    claims: list[str] = Field(default_factory=list)


class ClaimVerdict(BaseModel):
    claim: str = ""
    supported: bool = True
    reason: str = ""


class ClaimVerdicts(BaseModel):
    verdicts: list[ClaimVerdict] = Field(default_factory=list)


class GeneratedQuestions(BaseModel):
    questions: list[str] = Field(default_factory=list)


class CitationVerdict(BaseModel):
    citation_index: int = 0
    supported: bool = True
    reason: str = ""


class CitationVerdicts(BaseModel):
    verdicts: list[CitationVerdict] = Field(default_factory=list)


# --- pure functions (unit-tested with fixture verdicts) -----------------------


def faithfulness_score(supported_flags: list[bool]) -> float:
    """Empty claims -> 1.0 (nothing in the answer to be unfaithful about)."""
    if not supported_flags:
        return 1.0
    return sum(supported_flags) / len(supported_flags)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


def relevancy_score(similarities: list[float]) -> float:
    if not similarities:
        return 0.0
    return sum(similarities) / len(similarities)


def citation_faithfulness_score(supported_flags: list[bool]) -> float:
    if not supported_flags:
        return 1.0
    return sum(supported_flags) / len(supported_flags)


def extract_cited_sentences(answer: str) -> list[tuple[str, list[int]]]:
    """Sentences that carry at least one ``[n]`` citation marker, each paired
    with the list of citation indices found in it. Uncited sentences are
    excluded - there is nothing to check provenance for."""
    sentences = _SENTENCE_RE.split(answer)
    result = []
    for sentence in sentences:
        indices = [int(m) for m in _CITATION_RE.findall(sentence)]
        if indices:
            result.append((sentence.strip(), indices))
    return result


# --- LLM-judged scorers --------------------------------------------------------


async def judge_claims(
    claims: list[str], context: str, *, provider: LLMProvider
) -> list[ClaimVerdict]:
    """The claim-verdict half of faithfulness, split out from claim
    extraction (T-024's judge_calibration.py needs to hand a FROZEN,
    human-labeled claim list to the judge - claim extraction is itself an
    LLM call and would drift between runs, breaking positional alignment
    with hand-labels)."""
    if not claims:
        return []
    verdicts = await provider.extract(
        system_prompt=(
            "You are given a list of claims and a block of reference context. "
            "For each claim, decide whether the context supports it. A claim "
            "is supported only if the context states it or directly implies "
            "it - not if it merely doesn't contradict it.\n\n"
            f"Reference context:\n{context}\n\n"
            f"Claims:\n" + "\n".join(f"- {c}" for c in claims)
        ),
        user_input="Verdict each claim listed above.",
        schema=ClaimVerdicts,
    )
    # Fail closed on a judge miscount: a verdict list shorter than the claim
    # list must not silently shrink the denominator toward a passing score
    # (zero verdicts would otherwise grade as a perfect 1.0), and extras must
    # not inflate it.
    judged = list(verdicts.verdicts[: len(claims)])
    judged += [
        ClaimVerdict(claim=claim, supported=False, reason="judge returned no verdict; fail closed")
        for claim in claims[len(judged) :]
    ]
    return judged


async def score_faithfulness(
    answer: str, context: str, *, provider: LLMProvider
) -> list[ClaimVerdict]:
    claims = await provider.extract(
        system_prompt=(
            "Extract every individual factual claim made in the given answer, "
            "as a list of short standalone statements. Do not include hedges "
            "or meta-commentary, only concrete claims a reader could verify."
        ),
        user_input=answer,
        schema=ExtractedClaims,
    )
    return await judge_claims(claims.claims, context, provider=provider)


async def answer_relevancy(
    question: str, answer: str, *, provider: LLMProvider, embedder: Embedder
) -> float:
    generated = await provider.extract(
        system_prompt=(
            "Given the answer below, generate 3 questions this answer would be "
            "a good response to. Vary the phrasing."
        ),
        user_input=answer,
        schema=GeneratedQuestions,
    )
    if not generated.questions:
        return 0.0
    vectors = await embedder.embed([question, *generated.questions])
    question_vector, generated_vectors = vectors[0], vectors[1:]
    similarities = [cosine_similarity(question_vector, v) for v in generated_vectors]
    return relevancy_score(similarities)


async def score_citation_faithfulness(
    answer: str, chunks: list[dict[str, Any]], *, provider: LLMProvider
) -> list[CitationVerdict]:
    cited_sentences = extract_cited_sentences(answer)
    if not cited_sentences:
        return []

    deterministic: list[CitationVerdict] = []
    to_judge: list[tuple[str, int, str]] = []  # sentence, index, chunk content
    for sentence, indices in cited_sentences:
        for index in indices:
            if index < 1 or index > len(chunks):
                deterministic.append(
                    CitationVerdict(
                        citation_index=index, supported=False, reason="citation index out of range"
                    )
                )
                continue
            to_judge.append((sentence, index, chunks[index - 1]["content"]))

    if not to_judge:
        return deterministic

    pairs_block = "\n\n".join(
        f"[{index}] Sentence: {sentence!r}\nCited chunk: {chunk_content[:400]!r}"
        for sentence, index, chunk_content in to_judge
    )
    verdicts = await provider.extract(
        system_prompt=(
            "For each numbered pair below, decide whether the cited chunk "
            "actually supports the specific sentence it's attached to - not "
            "just the topic in general, the specific claim made.\n\n" + pairs_block
        ),
        user_input="Verdict each numbered pair above, using its number as citation_index.",
        schema=CitationVerdicts,
    )
    # Same fail-closed rule as score_faithfulness: one verdict per judged
    # pair, no more, no fewer - missing verdicts count as unsupported.
    judged = list(verdicts.verdicts[: len(to_judge)])
    judged += [
        CitationVerdict(
            citation_index=index, supported=False, reason="judge returned no verdict; fail closed"
        )
        for _, index, _ in to_judge[len(judged) :]
    ]
    return deterministic + judged


# --- graph driving + per-case orchestration ------------------------------------


async def _forced_knowledge_route(state: AgentState) -> dict[str, Any]:
    return {"route": "knowledge", "route_confidence": 1.0}


async def _answer_case(
    case: GenerationCase,
    *,
    tenant_id: UUID,
    conversation_id: UUID,
    provider: LLMProvider,
    embedder: Embedder,
    reranker: Reranker,
) -> tuple[str, list[dict[str, Any]]]:
    graph = build_graph(supervisor_node=_forced_knowledge_route)
    context = GraphContext(
        tenant_id=tenant_id, provider=provider, embedder=embedder, reranker=reranker
    )
    initial_state: AgentState = {
        "conversation_id": str(conversation_id),
        "tenant_id": str(tenant_id),
        "messages": [{"role": "customer", "content": case.question}],
        "route": None,
        "route_confidence": None,
        "retrieved_chunks": [],
        "selections": [],
        "engine_quote": None,
        "draft_response": "",
        "inspection": None,
        "escalated": False,
    }
    final_state = await graph.ainvoke(initial_state, context=context)
    return final_state["draft_response"], final_state["retrieved_chunks"]


@dataclass
class CaseResult:
    question: str
    answer: str
    refused: bool
    faithfulness: float | None = None
    relevancy: float | None = None
    citation_faithfulness: float | None = None
    claim_verdicts: list[ClaimVerdict] = field(default_factory=list)
    citation_verdicts: list[CitationVerdict] = field(default_factory=list)
    refusal_correct: bool | None = None


async def score_case(
    case: GenerationCase,
    answer: str,
    chunks: list[dict[str, Any]],
    *,
    provider: LLMProvider,
    embedder: Embedder,
) -> CaseResult:
    stripped = answer.strip()
    refused = stripped == REFUSAL_MESSAGE
    if case.negative:
        return CaseResult(
            question=case.question, answer=answer, refused=refused, refusal_correct=refused
        )
    if stripped in _NON_ANSWER_MESSAGES:
        # A positive case that got refused or escalated is a real failure,
        # not something to skip - score it as maximally unfaithful/irrelevant
        # rather than silently excluding it from the aggregate (an escalation
        # handoff has no claims and no citations, so the normal path below
        # would score it a perfect 1.0).
        return CaseResult(
            question=case.question,
            answer=answer,
            refused=refused,
            faithfulness=0.0,
            relevancy=0.0,
            citation_faithfulness=0.0,
        )

    context = "\n\n".join(chunk["content"] for chunk in chunks)
    claim_verdicts = await score_faithfulness(answer, context, provider=provider)
    relevancy = await answer_relevancy(case.question, answer, provider=provider, embedder=embedder)
    citation_verdicts = await score_citation_faithfulness(answer, chunks, provider=provider)

    return CaseResult(
        question=case.question,
        answer=answer,
        refused=False,
        faithfulness=faithfulness_score([v.supported for v in claim_verdicts]),
        relevancy=relevancy,
        citation_faithfulness=citation_faithfulness_score([v.supported for v in citation_verdicts]),
        claim_verdicts=claim_verdicts,
        citation_verdicts=citation_verdicts,
    )


async def _sync_eval_cases(conn: Any, tenant_id: UUID, cases: list[GenerationCase]) -> None:
    await conn.execute(
        "delete from eval_cases where tenant_id = $1 and case_type = 'generation'", tenant_id
    )
    for case in cases:
        await conn.execute(
            "insert into eval_cases (tenant_id, case_type, input, expected) "
            "values ($1, 'generation', $2, $3)",
            tenant_id,
            json.dumps({"question": case.question}),
            json.dumps(
                {
                    "reference_facts": case.reference_facts,
                    "expected_sources": case.expected_sources,
                    "negative": case.negative,
                }
            ),
        )


async def run_eval(
    *,
    tenant_id: UUID,
    cases: list[GenerationCase],
    provider: LLMProvider,
    embedder: Embedder,
    reranker: Reranker,
) -> tuple[dict[str, float], list[CaseResult]]:
    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        await _sync_eval_cases(conn, tenant_id, cases)
        # escalation.py writes real rows (escalations FKs conversations,
        # flips conversations.status), so every case needs a real
        # conversation row - a placeholder string would crash the whole run
        # at UUID() the first time Inspection double-fails a draft (the same
        # trap test_agent_graph.py's seeding helper documents).
        conversation_ids: list[UUID] = [
            await conn.fetchval(
                "insert into conversations (tenant_id) values ($1) returning id", tenant_id
            )
            for _ in cases
        ]

    results: list[CaseResult] = []
    for case, conversation_id in zip(cases, conversation_ids, strict=True):
        answer, chunks = await _answer_case(
            case,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            provider=provider,
            embedder=embedder,
            reranker=reranker,
        )
        results.append(await score_case(case, answer, chunks, provider=provider, embedder=embedder))

    positive = [r for r in results if r.faithfulness is not None]
    negative = [r for r in results if r.refusal_correct is not None]

    metrics: dict[str, float] = {
        "cases": float(len(results)),
        "positive_cases": float(len(positive)),
    }
    if positive:
        metrics["faithfulness"] = sum(r.faithfulness or 0.0 for r in positive) / len(positive)
        metrics["answer_relevancy"] = sum(r.relevancy or 0.0 for r in positive) / len(positive)
        metrics["citation_faithfulness"] = sum(
            r.citation_faithfulness or 0.0 for r in positive
        ) / len(positive)
    if negative:
        metrics["negative_cases"] = float(len(negative))
        metrics["refusal_accuracy"] = sum(1.0 for r in negative if r.refusal_correct) / len(
            negative
        )

    return metrics, results


def _git_sha() -> str:
    result = subprocess.run(  # noqa: S603 - fixed args, no shell, dev-tool only
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False
    )
    return result.stdout.strip()


async def _write_eval_run(conn: Any, tenant_id: UUID, metrics: dict[str, float]) -> None:
    git_sha = await run_in_threadpool(_git_sha)
    await conn.execute(
        "insert into eval_runs (tenant_id, run_type, metrics, git_sha) "
        "values ($1, 'generation', $2, $3)",
        tenant_id,
        json.dumps(metrics),
        git_sha,
    )


def _print_table(metrics: dict[str, float]) -> None:
    print(f"{'metric':<24}{'value'}")
    print("-" * 36)
    for key, value in metrics.items():
        print(f"{key:<24}{value:.3f}" if isinstance(value, float) else f"{key:<24}{value}")


def _print_verbose(results: list[CaseResult]) -> None:
    for result in results:
        print(f"\nQ: {result.question}")
        print(f"A: {result.answer}")
        if result.refusal_correct is not None:
            print(f"  refusal_correct={result.refusal_correct}")
            continue
        print(
            f"  faithfulness={result.faithfulness:.2f} "
            f"relevancy={result.relevancy:.2f} "
            f"citation_faithfulness={result.citation_faithfulness:.2f}"
        )
        for claim_verdict in result.claim_verdicts:
            if not claim_verdict.supported:
                print(f"  UNSUPPORTED CLAIM: {claim_verdict.claim!r} - {claim_verdict.reason}")
        for citation_verdict in result.citation_verdicts:
            if not citation_verdict.supported:
                print(
                    f"  BAD CITATION [{citation_verdict.citation_index}]: {citation_verdict.reason}"
                )


async def main_async(*, gate: bool, verbose: bool) -> int:
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
        provider = get_llm_provider()
        embedder = get_embedder(settings)
        reranker = get_reranker(settings)
        cases = load_cases()

        metrics, results = await run_eval(
            tenant_id=tenant_id,
            cases=cases,
            provider=provider,
            embedder=embedder,
            reranker=reranker,
        )

        async with db.tenant_context(tenant_id, "tenant_admin") as conn:
            await _write_eval_run(conn, tenant_id, metrics)

        _print_table(metrics)
        if verbose:
            _print_verbose(results)

        if gate:
            faithfulness = metrics.get("faithfulness", 0.0)
            relevancy = metrics.get("answer_relevancy", 0.0)
            if faithfulness < FAITHFULNESS_GATE or relevancy < RELEVANCY_GATE:
                print(
                    f"GATE FAILED: faithfulness {faithfulness:.3f} (>= {FAITHFULNESS_GATE}) / "
                    f"relevancy {relevancy:.3f} (>= {RELEVANCY_GATE})"
                )
                return 1
        return 0
    finally:
        if created_pool:
            await db.close_pool()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gate",
        action="store_true",
        help=f"exit non-zero if faithfulness < {FAITHFULNESS_GATE} or relevancy < {RELEVANCY_GATE}",
    )
    parser.add_argument("--verbose", action="store_true", help="print per-case detail")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main_async(gate=args.gate, verbose=args.verbose)))


if __name__ == "__main__":
    main()
