#!/usr/bin/env python3
"""Separate "the corpus got bigger" from "retrieval got better".

v5 will hold roughly twice v4's points. Recall and citation accuracy will move
on that alone, and a single before/after delta cannot say which happened. That
matters because the two call for opposite decisions: a volume effect means the
metric moved and the system did not, while a retrieval effect is the thing a
gate exists to detect.

The golden set cannot answer it either. Its predicates are phrases --
`{"contains": "reasonable restrictions"}` -- not document identities, which is
the weakness docs/03-EVIDENCE.md already records: "the golden set's predicates match
any passage containing a phrase, so a judgment quoting the section satisfies
the item". Recall@5 once read 0.927 while the governing provision was absent
from the top 100.

So this measures the haystack instead. For every golden-set phrase it counts
the documents and chunks containing it in each corpus version. An item whose
phrase matched three documents and now matches thirty has a different task in
front of it: finding one of thirty is easier, and recall improving there says
nothing about ranking. An item whose match count is unchanged is one where a
recall change is attributable to the system.

Reads the per-version chunk stores under data/legal_kb/processed, so it
touches no Qdrant, loads no model, and can run while a build is in progress --
though running it against an unfinished version reports a half corpus, which
is why it refuses unless told the version is complete.

Usage:
    python scripts/golden_set_haystack_report.py --before v4 --after v5
    python scripts/golden_set_haystack_report.py --before v4 --after v5 \
        --out docs/evidence/gates/haystack-v4-v5.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
CHUNK_ROOT = ROOT / "data" / "legal_kb" / "processed"
GOLDEN = ROOT / "data" / "legal_kb" / "evaluation" / "golden_set_v3.json"

# Above this, the item's phrase is so much easier to hit that a recall change
# on it cannot be read as a ranking change. Not tuned: the point is to
# separate "a handful" from "many", and anything near 2x already means the
# question being asked of retrieval has changed.
HAYSTACK_GROWTH_THRESHOLD = 2.0


def chunk_store(version: str) -> Path:
    name = version if version.startswith("global_legal_corpus") else f"global_legal_corpus_{version}"
    return CHUNK_ROOT / f"chunks.{name}"


def golden_phrases() -> list[tuple[str, str, list[str]]]:
    """(item id, question, phrases) for every item with phrase predicates."""
    document = json.loads(GOLDEN.read_text(encoding="utf-8"))
    items = document if isinstance(document, list) else document.get("questions") or document.get("items") or []
    rows: list[tuple[str, str, list[str]]] = []
    for item in items:
        phrases = [
            str(predicate["contains"]).strip().casefold()
            for predicate in item.get("relevant") or []
            if isinstance(predicate, dict) and predicate.get("contains")
        ]
        if phrases:
            rows.append((str(item.get("id")), str(item.get("question")), phrases))
    return rows


def iter_chunks(store: Path) -> Iterator[tuple[str, str]]:
    """(document id, lowercased chunk text) for every chunk a version indexed.

    Two details decide whether the counts mean anything.

    The store is written after the quality filter, so today every record in it
    is `quality == "indexed"` -- 51,300 records against 50,949 points for v5,
    49,745 against 49,684 for v4. The filter below is therefore a no-op now and
    a guard later: if the pipeline ever starts writing rejected chunks here,
    counting them would inflate the haystack with text no query can reach, and
    the inflation would look like corpus growth.

    The identity is the record's `document_id`, not the file's stem. The stem is
    the `canonical_document_id`, which groups duplicates of one instrument --
    the same Act from two ministries is one canonical id and two documents, with
    two official URLs. Citations are at document granularity, so the haystack
    has to be counted there too.
    """
    for path in sorted(store.glob("*.jsonl")):
        fallback_id = path.stem
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if "quality" in row and row.get("quality") != "indexed":
                    continue
                text = row.get("text") or row.get("embed_text") or ""
                if text:
                    yield str(row.get("document_id") or fallback_id), str(text).casefold()


def count_matches(store: Path, items: list[tuple[str, str, list[str]]]) -> dict[str, Any]:
    """Per item: how many documents and chunks its phrases can be found in.

    Counted as distinct documents matching ANY of the item's phrases, not the
    sum over phrases. Summing double-counts: several golden-set items list a
    section number and the phrase it contains, and a document holding both
    would be counted twice, so a corpus that merely re-chunked would appear to
    have grown.
    """
    documents: dict[str, set[str]] = {item_id: set() for item_id, _, _ in items}
    chunks: dict[str, int] = {item_id: 0 for item_id, _, _ in items}
    phrase_documents: dict[str, set[str]] = {
        phrase: set() for _, _, phrases in items for phrase in phrases
    }
    total_chunks = 0
    seen_documents: set[str] = set()

    for document_id, text in iter_chunks(store):
        total_chunks += 1
        seen_documents.add(document_id)
        for item_id, _, phrases in items:
            for phrase in phrases:
                if phrase in text:
                    documents[item_id].add(document_id)
                    chunks[item_id] += 1
                    phrase_documents[phrase].add(document_id)
                    # One hit places this chunk in the item's haystack; a
                    # second phrase in the same chunk is the same chunk.
                    break

    return {
        "items": {
            item_id: {"documents": len(documents[item_id]), "chunks": chunks[item_id]}
            for item_id, _, _ in items
        },
        "phrases": {phrase: len(matches) for phrase, matches in phrase_documents.items()},
        "corpus": {"documents": len(seen_documents), "chunks": total_chunks},
    }


def report(before: str, after: str) -> dict[str, Any]:
    items = golden_phrases()
    before_counts = count_matches(chunk_store(before), items)
    after_counts = count_matches(chunk_store(after), items)

    corpus_growth = (
        after_counts["corpus"]["chunks"] / before_counts["corpus"]["chunks"]
        if before_counts["corpus"]["chunks"]
        else None
    )

    rows: list[dict[str, Any]] = []
    for item_id, question, phrases in items:
        was = before_counts["items"][item_id]["documents"]
        now = after_counts["items"][item_id]["documents"]
        growth = (now / was) if was else None
        rows.append(
            {
                "id": item_id,
                "question": question,
                "phrases": phrases,
                "documents_before": was,
                "documents_after": now,
                "chunks_before": before_counts["items"][item_id]["chunks"],
                "chunks_after": after_counts["items"][item_id]["chunks"],
                "growth": round(growth, 2) if growth is not None else None,
                # What a reader of the gate needs: whether a recall change on
                # this item can be attributed to the system at all. An item
                # whose haystack grew faster than the corpus did got easier for
                # reasons that have nothing to do with ranking.
                "recall_change_attributable_to_retrieval": (
                    growth is not None and growth < HAYSTACK_GROWTH_THRESHOLD
                ),
                "grew_faster_than_the_corpus": (
                    growth is not None
                    and corpus_growth is not None
                    and growth > corpus_growth
                ),
                "newly_findable": was == 0 and now > 0,
                "still_absent": now == 0,
            }
        )

    # Three buckets, not two. An item absent from both corpora has no growth
    # ratio, and calling that "the haystack grew" -- as an earlier version of
    # this did -- reported 21 items that nothing matches as 21 items that got
    # easier.
    attributable = [row for row in rows if row["recall_change_attributable_to_retrieval"]]
    grew = [row for row in rows if row["growth"] is not None and not row["recall_change_attributable_to_retrieval"]]
    no_baseline = [row for row in rows if row["growth"] is None]
    return {
        "before": before,
        "after": after,
        "golden_set": GOLDEN.name,
        "items": len(rows),
        "growth_threshold": HAYSTACK_GROWTH_THRESHOLD,
        "corpus": {
            "before": before_counts["corpus"],
            "after": after_counts["corpus"],
            "chunk_growth": round(corpus_growth, 3) if corpus_growth is not None else None,
        },
        "summary": {
            "items_where_recall_change_is_attributable": len(attributable),
            "items_whose_haystack_grew": len(grew),
            "items_with_no_before_baseline": len(no_baseline),
            "items_newly_findable": sum(1 for row in rows if row["newly_findable"]),
            "items_still_absent": sum(1 for row in rows if row["still_absent"]),
        },
        "phrases_before": before_counts["phrases"],
        "phrases_after": after_counts["phrases"],
        "rows": sorted(rows, key=lambda row: -(row["growth"] or 0)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--before", required=True, help="corpus version, e.g. v4")
    parser.add_argument("--after", required=True, help="corpus version, e.g. v5")
    parser.add_argument("--out", type=Path)
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Report on a version still being built. The counts are a half corpus.",
    )
    args = parser.parse_args()

    for version in (args.before, args.after):
        store = chunk_store(version)
        if not store.is_dir():
            print(f"no chunk store at {store}", file=sys.stderr)
            return 2

    if not args.allow_incomplete:
        # A version mid-build has fewer documents than its manifest, and a
        # haystack count taken then understates the after side on every row.
        manifest = ROOT / "data" / "legal_kb" / "metadata" / "canonical_documents.jsonl"
        if manifest.exists():
            expected = len({json.loads(line)["canonical_document_id"] for line in manifest.read_text().splitlines() if line.strip()})
            written = len(list(chunk_store(args.after).glob("*.jsonl")))
            if written < expected:
                print(
                    f"{args.after} has {written} of {expected} documents written; "
                    "its haystack counts would understate every row. Pass "
                    "--allow-incomplete to report anyway.",
                    file=sys.stderr,
                )
                return 2

    result = report(args.before, args.after)
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n", encoding="utf-8")
        print(f"Wrote {args.out}")

    corpus = result["corpus"]
    print(
        f"corpus: {corpus['before']['documents']} docs / {corpus['before']['chunks']} chunks"
        f"  ->  {corpus['after']['documents']} docs / {corpus['after']['chunks']} chunks"
        f"  ({corpus['chunk_growth']}x)"
    )
    print("Read every item growth below against that corpus figure, not against 1.0x.")
    print()
    print(json.dumps(result["summary"], indent=2, sort_keys=True))
    print()
    print("Items whose haystack grew most -- a recall change on these is volume, not ranking:")
    for row in result["rows"][:10]:
        if row["growth"] and row["growth"] >= HAYSTACK_GROWTH_THRESHOLD:
            print(
                f"  {row['growth']:5.1f}x  {row['documents_before']:4} -> {row['documents_after']:4} docs  {row['id']}"
            )
    still_absent = [row for row in result["rows"] if row["still_absent"]]
    if still_absent:
        print()
        print("Items no document matches even after the rebuild:")
        for row in still_absent:
            print(f"  {row['id']}: {row['phrases']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
