#!/usr/bin/env python3
"""Measure retrieval quality against the golden set.

Every quality claim about this system so far has been reasoned from a handful
of hand-run queries. This produces numbers instead: Recall@k, nDCG, MRR, and
abstention accuracy, across the four configurations the PRD asks for.

Configurations:
    dense       dense vectors only
    sparse      learned-sparse only
    hybrid      dense + sparse fused server-side with RRF   (the Fast lane)
    reranked    hybrid, then the cross-encoder              (the Deep lane)

Usage:
    python scripts/evaluate_retrieval.py
    python scripts/evaluate_retrieval.py --configs hybrid reranked
    python scripts/evaluate_retrieval.py --collection global_legal_corpus_v2 \
        --out docs/evidence/retrieval-eval-v2.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

DEFAULT_GOLDEN = ROOT / "data" / "legal_kb" / "evaluation" / "golden_set_v3.json"

CONFIGS = ("dense", "sparse", "hybrid", "reranked")

# The abstention rule the Fast lane actually applies, restated here so the
# harness measures deployed behaviour rather than an idealised version of it.
# Imported from the lane so the harness cannot drift from deployed behaviour.
from app.services.fast_research import COVERAGE_FLOOR as ABSTAIN_COVERAGE_FLOOR  # noqa: E402


async def _retrieve(
    service: Any,
    query: str,
    *,
    config: str,
    collection: str,
    limit: int,
) -> list[dict[str, Any]]:
    from app.services.retrieval import RetrievalFilters, RetrievalTarget

    filters = RetrievalFilters(corpus_tiers=["gold", "extended"])
    target = RetrievalTarget(collection_name=collection, filters=filters)

    if config in {"dense", "sparse"}:
        # Single-vector search, bypassing fusion, to isolate what each signal
        # contributes. Uses the service's own embedding path so the comparison
        # is against production behaviour rather than a reimplementation.
        from app.core.config import settings
        from app.ingestion.sparse import to_sparse_vector

        embedding = await service._embed_query_batched(query)
        if config == "dense":
            vector, using = embedding.dense, settings.qdrant_dense_vector_name
        else:
            vector, using = (
                to_sparse_vector(embedding.sparse),
                settings.qdrant_sparse_vector_name,
            )
        response = await service.client.query_points(
            collection_name=collection,
            query=vector,
            using=using,
            query_filter=filters.to_qdrant(),
            limit=limit,
            with_payload=True,
        )
        return [dict(point.payload or {}) for point in response.points]

    hits, _ = await service.search_across_collections_with_timings(
        query,
        targets=[target],
        candidate_limit=max(limit, 20),
        result_limit=limit,
        rerank=(config == "reranked"),
    )
    return [hit.payload for hit in hits]


async def _abstained(
    service: Any,
    question: str,
    payloads: list[dict[str, Any]],
    *,
    collection: str,
) -> bool:
    """Whether the Fast lane's relevance gate would leave nothing to publish.

    Both halves of the gate, not just the floor. An earlier version applied
    only `_lexical_coverage`, while claiming in a comment to measure deployed
    behaviour -- so it scored an idealised lane and would have credited the
    mandatory-term requirement with nothing.
    """
    from app.services.fast_research import (
        COVERAGE_FLOOR,
        COVERAGE_FLOOR_WITHOUT_RARE_TERM,
        _focus_tokens,
        _lexical_coverage,
        _locally_matched_focus_terms,
        _mandatory_focus_match,
    )
    from app.services.retrieval import RetrievalFilters, RetrievalTarget

    if not payloads:
        return True
    focus = _focus_tokens(question)
    _, distinctive = await service.distinctive_query_terms(
        focus,
        target=RetrievalTarget(
            collection_name=collection,
            filters=RetrievalFilters(corpus_tiers=["gold", "extended"]),
        ),
    )
    required = set(distinctive)
    # Mirrors the lane: with no rare term to prove a corpus gap, coverage is
    # the only remaining signal and carries a higher bar.
    floor = COVERAGE_FLOOR if required else COVERAGE_FLOOR_WITHOUT_RARE_TERM
    return not any(
        _lexical_coverage(focus, payload) >= floor
        and _mandatory_focus_match(
            required, _locally_matched_focus_terms(focus, payload)
        )
        for payload in payloads
    )


async def evaluate(
    *, collection: str, golden: Path, configs: tuple[str, ...], limit: int
) -> dict[str, Any]:
    from app.evaluation.golden_set import load_golden_set, score
    from app.services.retrieval import HybridRetrievalService

    items = load_golden_set(golden)
    answerable = [item for item in items if item.expectation == "answer"]
    abstentions = [item for item in items if item.expectation == "abstain"]
    print(
        f"golden set: {len(items)} items "
        f"({len(answerable)} answerable, {len(abstentions)} expected abstentions)\n"
    )

    service = HybridRetrievalService()
    report: dict[str, Any] = {}
    try:
        await service.warmup()
        for config in configs:
            started = time.perf_counter()
            results = []
            abstain_correct = 0
            false_abstentions = 0
            per_item: list[dict[str, Any]] = []

            for item in items:
                payloads = await _retrieve(
                    service,
                    item.question,
                    config=config,
                    collection=collection,
                    limit=limit,
                )
                if item.expectation == "abstain":
                    correct = await _abstained(
                        service, item.question, payloads, collection=collection
                    )
                    abstain_correct += correct
                    per_item.append(
                        {"id": item.id, "expectation": "abstain", "abstained": correct}
                    )
                    continue
                outcome = score(item, payloads)
                results.append(outcome)
                # The cost side of the abstention gate. Tightening it to
                # decline more corpus gaps is only an improvement if it does
                # not also start declining questions the corpus can answer,
                # and that trade is invisible if only gaps are scored.
                wrongly_declined = await _abstained(
                    service, item.question, payloads, collection=collection
                )
                if wrongly_declined:
                    false_abstentions += 1
                per_item.append(
                    {
                        "id": item.id,
                        "role": item.role,
                        "expectation": "answer",
                        "first_rank": outcome.first_rank,
                        "recall_at_5": outcome.recall_at(5),
                        "recall_at_20": outcome.recall_at(20),
                        "citation_accuracy_at_5": outcome.precision_at(5),
                        "wrongly_abstained": wrongly_declined,
                    }
                )

            elapsed = time.perf_counter() - started
            summary = {
                "recall_at_1": statistics.mean(r.recall_at(1) for r in results),
                "recall_at_5": statistics.mean(r.recall_at(5) for r in results),
                "recall_at_20": statistics.mean(r.recall_at(20) for r in results),
                "mrr": statistics.mean(r.reciprocal_rank() for r in results),
                "ndcg_at_10": statistics.mean(r.ndcg_at(10) for r in results),
                "citation_accuracy_at_5": statistics.mean(
                    r.precision_at(5) for r in results
                ),
                "abstention_accuracy": (
                    abstain_correct / len(abstentions) if abstentions else None
                ),
                "false_abstention_rate": (
                    false_abstentions / len(answerable) if answerable else None
                ),
                "seconds_per_query": elapsed / max(len(items), 1),
            }
            # Reported per role: police and advocate ask differently shaped
            # questions, and a whole-set average lets one audience hide behind
            # another.
            by_role: dict[str, Any] = {}
            for role in sorted({item.role for item in answerable}):
                scoped = [r for r in results if r.item.role == role]
                if not scoped:
                    continue
                by_role[role] = {
                    "items": len(scoped),
                    "recall_at_5": round(statistics.mean(r.recall_at(5) for r in scoped), 3),
                    "recall_at_20": round(statistics.mean(r.recall_at(20) for r in scoped), 3),
                    "citation_accuracy_at_5": round(
                        statistics.mean(r.precision_at(5) for r in scoped), 3
                    ),
                }
            summary["by_role"] = by_role
            report[config] = {"summary": summary, "items": per_item}

            print(f"--- {config} ---")
            print(
                f"  R@1 {summary['recall_at_1']:.2f}   "
                f"R@5 {summary['recall_at_5']:.2f}   "
                f"R@20 {summary['recall_at_20']:.2f}   "
                f"MRR {summary['mrr']:.3f}   "
                f"nDCG@10 {summary['ndcg_at_10']:.3f}"
            )
            print(f"  citation accuracy@5 {summary['citation_accuracy_at_5']:.2f}")
            for role, scores in summary["by_role"].items():
                print(
                    f"    {role:<9} n={scores['items']:<3} "
                    f"R@5 {scores['recall_at_5']:.2f}  R@20 {scores['recall_at_20']:.2f}  "
                    f"cite@5 {scores['citation_accuracy_at_5']:.2f}"
                )
            abstention = summary["abstention_accuracy"]
            false_rate = summary["false_abstention_rate"]
            trailer = f"  {summary['seconds_per_query'] * 1000:.0f} ms/query"
            if false_rate is not None:
                trailer = f"  wrongly declined {false_rate:.2f}" + trailer
            if abstention is not None:
                trailer = f"  abstention {abstention:.2f}" + trailer
            print(trailer)

            missed = [
                row["id"]
                for row in per_item
                if row["expectation"] == "answer" and not row["recall_at_20"]
            ]
            if missed:
                print(f"  missed entirely : {', '.join(missed)}")
            wrongly_declined_ids = [
                row["id"]
                for row in per_item
                if row["expectation"] == "answer" and row.get("wrongly_abstained")
            ]
            if wrongly_declined_ids:
                print(f"  declined an answerable question: {', '.join(wrongly_declined_ids)}")
            wrongly_answered = [
                row["id"]
                for row in per_item
                if row["expectation"] == "abstain" and not row["abstained"]
            ]
            if wrongly_answered:
                print(f"  answered a gap  : {', '.join(wrongly_answered)}")
            print()
    finally:
        await service.close()
    return report


def _measurement_config() -> dict[str, Any]:
    """What this measurement was taken under."""
    from app.agents.prompt_registry import prompt_versions
    from app.core.config import settings

    return {
        "embedding_model": settings.embedding_model,
        "embedding_dimension": settings.embedding_dimension,
        "generation_model": settings.ollama_model,
        "reranker_input_characters": _reranker_budget(),
        "repealed_rank_penalty": settings.repealed_rank_penalty,
        "abstain_coverage_floor": ABSTAIN_COVERAGE_FLOOR,
        "prompt_versions": prompt_versions(),
    }


def _reranker_budget() -> int:
    from app.services.retrieval import RERANKER_INPUT_CHARACTERS

    return RERANKER_INPUT_CHARACTERS


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", default="global_legal_corpus")
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--configs", nargs="+", default=list(CONFIGS), choices=CONFIGS)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--out", type=Path)
    arguments = parser.parse_args()

    report = asyncio.run(
        evaluate(
            collection=arguments.collection,
            golden=arguments.golden,
            configs=tuple(arguments.configs),
            limit=arguments.limit,
        )
    )

    if arguments.out:
        arguments.out.parent.mkdir(parents=True, exist_ok=True)
        arguments.out.write_text(
            json.dumps(
                {
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "collection": arguments.collection,
                    "golden_set": arguments.golden.name,
                    "limit": arguments.limit,
                    # The configuration a result was taken under, so a number
                    # can be reproduced or explained rather than only quoted.
                    # Retrieval sends no prompt, but the prompt versions are
                    # recorded anyway: a result is only comparable to another
                    # taken under the same build of the system.
                    "config": _measurement_config(),
                    "configs": report,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"wrote {arguments.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
