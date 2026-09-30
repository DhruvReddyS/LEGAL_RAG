#!/usr/bin/env python3
"""What the deployed index actually contains.

Three documents quoted three different sizes for the same collection -- 24,810,
25,323 and 25,517 -- because each was written by hand on a different day and
none of them was wrong when it was written. Counts belong to the index, not to
prose, so this asks the index and records the answer.

    python scripts/corpus_inventory.py                      # read and record
    python scripts/corpus_inventory.py --check              # fail on drift
    python scripts/corpus_inventory.py --collection NAME    # another collection
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
RECORD = ROOT / "docs" / "evidence" / "corpus-inventory.json"
MANIFEST = ROOT / "data" / "legal_kb" / "metadata" / "canonical_documents.jsonl"

# Counted in full rather than sampled: a sample of a corpus this size gives a
# number that moves between runs, and a moving number is what caused the drift.
SCROLL_PAGE = 1000


def _post(url: str, body: dict, timeout: float = 30.0) -> dict:
    request = urllib.request.Request(
        url, data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def read_index(base_url: str, collection: str) -> dict:
    total = _post(f"{base_url}/collections/{collection}/points/count", {"exact": True})["result"]["count"]

    acts: Counter[str] = Counter()
    tiers: Counter[str] = Counter()
    offset = None
    seen = 0
    while True:
        body = {"limit": SCROLL_PAGE, "with_payload": ["act_name", "corpus_tier"], "with_vector": False}
        if offset is not None:
            body["offset"] = offset
        page = _post(f"{base_url}/collections/{collection}/points/scroll", body)["result"]
        for point in page["points"]:
            payload = point.get("payload") or {}
            acts[str(payload.get("act_name") or "(unnamed)").strip()] += 1
            tiers[str(payload.get("corpus_tier") or "(none)").strip()] += 1
        seen += len(page["points"])
        offset = page.get("next_page_offset")
        if offset is None:
            break
    return {"points": total, "points_seen": seen, "acts": acts, "tiers": tiers}


def read_manifest() -> dict:
    from app.ingestion.metadata import iter_canonical_documents, load_manifest

    documents = load_manifest(MANIFEST)
    return {
        "physical_documents": len(documents),
        "canonical_documents": len(list(iter_canonical_documents(documents))),
    }


def build(base_url: str, collection: str) -> dict:
    index = read_index(base_url, collection)
    manifest = read_manifest()
    # The three replaced codes against the three that replaced them: the ratio
    # that decides which law retrieval meets first.
    #
    # Matched on the whole act name. A substring search for "Indian Evidence
    # Act" also collects the Law Commission's review of that Act and a paper on
    # privilege under it, which between them add 1,071 passages of commentary
    # to what would then be reported as the statute. Matching on the opening of
    # the name is not enough either: it pulls in the CrPC Amendment Act, which
    # is a different instrument. A name absent from the index reports zero,
    # which is visible, rather than silently matching nothing.
    def totals_for(names: tuple[str, ...]) -> dict:
        return {name.split(",")[0]: index["acts"].get(name, 0) for name in names}

    in_force = (
        "THE BHARATIYA NYAYA SANHITA, 2023",
        "THE BHARATIYA NAGARIK SURAKSHA SANHITA, 2023",
        "THE BHARATIYA SAKSHYA ADHINIYAM, 2023",
    )
    repealed = tuple(
        act for act in index["acts"]
        if act.startswith("The Indian Penal Code Act, 1860")
        or act.startswith("The Code of Criminal Procedure, 1973 (Act No.2 of 1974)")
        or act.startswith("The Indian Evidence Act, 1872 1977")
    )

    return {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "collection": collection,
        "points": index["points"],
        **manifest,
        "points_by_tier": dict(sorted(index["tiers"].items(), key=lambda item: -item[1])),
        # All of them: eighty names is small enough to record in full, and a
        # truncated list is how a variant spelling goes unnoticed.
        "acts": dict(index["acts"].most_common()),
        "distinct_acts": len(index["acts"]),
        "points_by_code_in_force": totals_for(in_force),
        "points_by_code_repealed": totals_for(repealed),
        "points_in_force_codes": sum(totals_for(in_force).values()),
        "points_repealed_codes": sum(totals_for(repealed).values()),
    }


def main() -> int:
    from app.core.config import settings

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", default=settings.qdrant_global_collection)
    parser.add_argument("--qdrant", default="http://localhost:6333")
    parser.add_argument("--check", action="store_true", help="fail if the record disagrees with the index")
    arguments = parser.parse_args()

    try:
        live = build(arguments.qdrant, arguments.collection)
    except (urllib.error.URLError, TimeoutError) as error:
        print(f"could not reach Qdrant at {arguments.qdrant}: {error}")
        return 2

    print(f"collection        {live['collection']}")
    print(f"points            {live['points']:,}")
    print(f"physical docs     {live['physical_documents']}")
    print(f"canonical docs    {live['canonical_documents']}")
    print(f"distinct acts     {live['distinct_acts']}")
    print(f"in-force codes    {live['points_in_force_codes']:,} points")
    print(f"repealed codes    {live['points_repealed_codes']:,} points")
    for tier, count in live["points_by_tier"].items():
        print(f"  tier {tier:<12} {count:,}")

    if arguments.check:
        if not RECORD.is_file():
            print(f"\nno record at {RECORD.relative_to(ROOT)}; run without --check to create it")
            return 1
        recorded = json.loads(RECORD.read_text(encoding="utf-8"))
        drifted = [
            field for field in ("collection", "points", "physical_documents", "canonical_documents")
            if recorded.get(field) != live[field]
        ]
        if drifted:
            print("\nDRIFT: the recorded inventory no longer matches the index")
            for field in drifted:
                print(f"  {field}: recorded {recorded.get(field)!r}, live {live[field]!r}")
            return 1
        print("\nrecorded inventory matches the index")
        return 0

    RECORD.write_text(json.dumps(live, indent=2) + "\n", encoding="utf-8")
    print(f"\nrecorded {RECORD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
