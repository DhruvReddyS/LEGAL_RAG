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

DEFAULT_GOLDEN = ROOT / "data" / "legal_kb" / "evaluation" / "golden_set_v1.json"

CONFIGS = ("dense", "sparse", "hybrid", "reranked")

# The abstention rule the Fast lane actually applies, restated here so the
# harness measures deployed behaviour rather than an idealised version of it.
ABSTAIN_COVERAGE_FLOOR = 0.34


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


def _abstained(question: str, payloads: list[dict[str, Any]]) -> bool:
    """Whether the Fast lane's relevance gate would leave nothing to publish."""
    from app.services.fast_research import _focus_tokens, _lexical_coverage

    if not payloads:
        return True
    focus = _focus_tokens(question)
    return not any(
        _lexical_coverage(focus, payload) >= ABSTAIN_COVERAGE_FLOOR
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
                    correct = _abstained(item.question, payloads)
                    abstain_correct += correct
                    per_item.append(
                        {"id": item.id, "expectation": "abstain", "abstained": correct}
                    )
                    continue
                outcome = score(item, payloads)
                results.append(outcome)
                per_item.append(
                    {
                        "id": item.id,
                        "expectation": "answer",
                        "first_rank": outcome.first_rank,
                        "recall_at_5": outcome.recall_at(5),
                        "recall_at_20": outcome.recall_at(20),
                    }
                )

            elapsed = time.perf_counter() - started
            summary = {
                "recall_at_1": statistics.mean(r.recall_at(1) for r in results),
                "recall_at_5": statistics.mean(r.recall_at(5) for r in results),
                "recall_at_20": statistics.mean(r.recall_at(20) for r in results),
                "mrr": statistics.mean(r.reciprocal_rank() for r in results),
                "ndcg_at_10": statistics.mean(r.ndcg_at(10) for r in results),
                "abstention_accuracy": (
                    abstain_correct / len(abstentions) if abstentions else None
                ),
                "seconds_per_query": elapsed / max(len(items), 1),
            }
            report[config] = {"summary": summary, "items": per_item}

            print(f"--- {config} ---")
            print(
                f"  R@1 {summary['recall_at_1']:.2f}   "
                f"R@5 {summary['recall_at_5']:.2f}   "
                f"R@20 {summary['recall_at_20']:.2f}   "
                f"MRR {summary['mrr']:.3f}   "
                f"nDCG@10 {summary['ndcg_at_10']:.3f}"
            )
            abstention = summary["abstention_accuracy"]
            trailer = f"  {summary['seconds_per_query'] * 1000:.0f} ms/query"
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
