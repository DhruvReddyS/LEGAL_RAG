#!/usr/bin/env python3
"""Can retrieval reach the provision that governs the question?

The instrument the golden set does not provide. Relevance predicates match
any passage *containing* a phrase, so a judgment quoting BNSS s.173 satisfies
the FIR item while the section itself is absent from the top 100. Recall@5
read 0.927 while the governing provision was unreachable for four of six core
questions.

This asks the other question directly: for a named question, does the named
provision appear in what retrieval returns, and at what rank. It is cheap --
no model, embeddings only -- so it can run beside the answer evaluation
rather than instead of it.

Usage:
    python scripts/check_provision_reach.py
    python scripts/check_provision_reach.py --record
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
BASELINE = ROOT / "docs" / "evidence" / "provision-reach-baseline.json"

# Question, and the provision that actually governs it. Each was read out of
# the Act rather than taken from what the system happens to return.
CASES: list[tuple[str, str, str]] = [
    ("How is an FIR registered?", "BNSS", "173"),
    ("When can the police arrest someone without a warrant?", "BNSS", "35"),
    ("On what grounds may anticipatory bail be granted?", "BNSS", "482"),
    ("What is default bail?", "BNSS", "187"),
    ("Which law now governs the offence of theft?", "BNS", "303"),
    ("Is a statement made by a dying person accepted as evidence?", "BSA", "26"),
    ("Must the grounds of arrest be communicated to the arrested person?", "BNSS", "47"),
    ("What safeguards apply when a woman is arrested?", "BNSS", "43"),
]

_ALIAS = {"BNSS": "nagarik suraksha", "BNS": "nyaya sanhita", "BSA": "sakshya adhiniyam"}


async def measure() -> dict:
    from app.core.config import settings
    from app.services.retrieval import (
        HybridRetrievalService, RetrievalFilters, RetrievalTarget,
    )

    service = HybridRetrievalService()
    await service.warmup()
    target = RetrievalTarget(
        collection_name=settings.qdrant_global_collection,
        filters=RetrievalFilters(corpus_tiers=["gold", "extended"]),
    )
    rows = []
    try:
        for question, code, section in CASES:
            hits, _ = await service.search_across_collections_with_timings(
                question, targets=[target], candidate_limit=40, result_limit=8
            )
            followed = await service.fetch_followed_provisions(
                hits,
                target=target,
                query=question,
            )
            merged = hits + followed
            rank = next(
                (
                    index
                    for index, hit in enumerate(merged, 1)
                    if _ALIAS[code] in str(hit.payload.get("act_name", "")).lower()
                    and str(hit.payload.get("section")) == section
                ),
                None,
            )
            rows.append(
                {
                    "question": question,
                    "provision": f"{code} s.{section}",
                    "rank": rank,
                    "reached": rank is not None,
                    "via_citation_following": bool(followed) and rank is not None
                    and rank > len(hits),
                }
            )
    finally:
        await service.close()

    reached = sum(row["reached"] for row in rows)
    return {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "collection": __import__("app.core.config", fromlist=["settings"]).settings.qdrant_global_collection,
        "reached": reached,
        "total": len(rows),
        "reach_rate": round(reached / len(rows), 3),
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", action="store_true")
    arguments = parser.parse_args()

    report = asyncio.run(measure())
    print(f"\n{'question':<52}{'provision':<12}{'rank':>6}")
    print("-" * 72)
    for row in report["rows"]:
        print(f"{row['question'][:50]:<52}{row['provision']:<12}"
              f"{str(row['rank'] or '—'):>6}{'  (followed)' if row['via_citation_following'] else ''}")
    print(f"\nreached {report['reached']}/{report['total']}  ({report['reach_rate']:.0%})")

    if arguments.record:
        BASELINE.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"recorded {BASELINE.relative_to(ROOT)}")
        return 0

    if BASELINE.is_file():
        previous = json.loads(BASELINE.read_text(encoding="utf-8"))
        was = {r["provision"]: r["reached"] for r in previous["rows"]}
        lost = [
            r["provision"] for r in report["rows"]
            if was.get(r["provision"]) and not r["reached"]
        ]
        if lost:
            print(f"\nREGRESSION: no longer reachable -- {', '.join(lost)}")
            return 1
        print("\nno provision became unreachable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
