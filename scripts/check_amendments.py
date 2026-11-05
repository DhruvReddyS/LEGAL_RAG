#!/usr/bin/env python3
"""Compare the watched Acts against local source lists and write findings for review.

Works offline, with no database: the default run uses only files in this repository.
Pass --fetch to also ask each official host about its file. That sends HEAD requests
only, to hosts already in the source lists, with a timeout. A host that refuses is
reported and left alone.

    check_amendments.py
    check_amendments.py --fetch --fetch-limit 25 --timeout 15

Findings go to <kb-root>/logs/amendment_findings.json, which the admin console reads.
The manifest and the currency table are never changed.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import settings  # noqa: E402
from app.services import amendment_watch  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--kb-root", type=Path, help="Corpus root. Defaults to LEGAL_KB_ROOT.")
    parser.add_argument("--sources-dir", type=Path, default=ROOT / "data/source_materials")
    parser.add_argument("--candidates-dir", type=Path, help="Local copies to checksum. Defaults to <sources-dir>/candidate_imports.")
    parser.add_argument("--output-root", type=Path, help="Where logs/ goes. Defaults to the corpus root.")
    parser.add_argument("--fetch", action="store_true", help="Also send HEAD requests to official hosts.")
    parser.add_argument("--fetch-limit", type=int, default=25)
    parser.add_argument("--timeout", type=float, default=15.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = (args.kb_root or Path(settings.legal_kb_root)).resolve()
    if not (root / "metadata/canonical_documents.jsonl").is_file():
        print(f"No manifest under {root}", file=sys.stderr)
        return 2
    report = amendment_watch.run_check(
        root,
        args.sources_dir,
        output_root=args.output_root,
        candidates_dir=args.candidates_dir or args.sources_dir / "candidate_imports",
        fetch=args.fetch,
        fetch_limit=args.fetch_limit,
        timeout=args.timeout,
    )
    coverage = report["coverage"]
    print(f"Checked at {report['checked_at']} ({report['mode']})")
    print(f"Watched Acts: {report['watched']}, against {report['source_entries']} source-list entries")
    print(f"  compared with a local source: {coverage.get('checked', 0)}")
    print(f"  no local source to compare:   {coverage.get('no_local_source', 0)}")
    if args.fetch:
        print(f"  network: {report['fetch']}")
    else:
        print("  network: not used. Nothing here says whether an official site has changed.")
    kinds = Counter(item["kind"] for item in report["findings"])
    print(f"Findings for review: {len(report['findings'])}")
    for kind, count in sorted(kinds.items()):
        print(f"  {kind}: {count}")
    print(f"Written to {(args.output_root or root) / amendment_watch.REPORT_RELATIVE}")
    print("These are disagreements between records, not statements of the law. A person decides.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
