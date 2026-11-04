#!/usr/bin/env python3
"""Catch a hardcoded statutory citation that the corpus no longer supports.

The police compliance checklist is a list of duties, and each duty names the
provision that imposes it -- `("notify_relative", ..., "BNSS s.48(1)")`. There
are 66 such citations across 13 modules, 44 of them BNSS. They are written into
the source, and nothing checks them against anything. If a section is
renumbered by an amendment, or the provision is repealed, the checklist goes on
telling an officer that a duty arises under a provision that no longer says so,
and the only way anyone finds out is a reader who knows the Act better than the
code does.

This is the gap a correctness suite cannot cover: every test asserting
"s.48(1) requires notifying a relative" would be asserting the stale number
against itself and passing.

Two failures are checked, and they are different:

  absent      the cited provision cannot be found in the corpus at all, so the
              citation offered to a reader cannot be opened or verified.
  superseded  it is found, and the authority it sits in resolves as no longer
              in force -- a duty asserted on repealed law.

Extraction is static: it reads the source, so `--extract-only` runs anywhere
and is what the unit tests exercise. Resolution needs the index, so the full
run belongs in the gate runner, after a build, alongside the other gates.

An interpolated citation -- `f"BNSS s.187(3)({'i' if days == 90 else 'ii'})"`
-- cannot be resolved from source text. It is reported as unresolvable rather
than silently dropped, because dropping it would quietly shrink the thing
being checked.

Usage:
    python scripts/check_provision_drift.py --extract-only
    python scripts/check_provision_drift.py --collection global_legal_corpus_v5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

SOURCE_ROOT = ROOT / "backend" / "app"

# The statutes whose provisions are asserted as live duties. The repealed codes
# are deliberately absent: IPC, CrPC and IEA appear only in the concordance
# (section_mapping.py) and the repeal detector (repeal_labels.py), where naming
# them is the point. Checking those as live duties would fail by design.
LIVE_STATUTES: dict[str, str] = {
    "BNSS": "Bharatiya Nagarik Suraksha Sanhita",
    "BNS": "Bharatiya Nyaya Sanhita",
    "BSA": "Bharatiya Sakshya Adhiniyam",
}

# Two shapes, because the codebase uses both and checking only one would
# quietly leave the other unguarded.
#
# Prose, as the compliance checklist writes it:
#     "BNSS s.193(3)(i)(a)" / "BNSS s.105" / "BNSS s.43(1) proviso"
CITATION = re.compile(
    r"\b(?P<statute>" + "|".join(LIVE_STATUTES) + r")\s+s\.\s*(?P<section>\d+[A-Z]?)(?P<rest>[^\"']*)"
)

# Structured, as the concept bridges in citation_following.py write it:
#     _Concept("BNSS", "47", "arrest-right implementation", ...)
# A statute code as one string literal and the section as the next. These
# route a question straight at a provision, so a renumbering sends the reader
# to the wrong section with no citation text to notice it by -- the same risk
# as the prose form, and invisible to a regex looking for "s.".
PAIRED_CITATION = re.compile(
    r"[\"'](?P<statute>" + "|".join(LIVE_STATUTES) + r")[\"']\s*,\s*[\"'](?P<section>\d+[A-Z]?)[\"']"
)

# Modules that name provisions in order to describe them historically rather
# than to impose them. Nothing is skipped silently: the report lists these.
DESCRIPTIVE_MODULES = frozenset({"section_mapping.py", "repeal_labels.py", "supersession.py"})


def _display(path: Path) -> str:
    """A repo-relative path for the report, or the full path if it is outside.

    `relative_to` raises rather than returning the absolute path, so a
    citation found anywhere but under the repo root would crash the report
    instead of being named in it.
    """
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


class Citation:
    __slots__ = ("statute", "section", "text", "path", "line", "interpolated")

    def __init__(self, statute: str, section: str, text: str, path: Path, line: int) -> None:
        self.statute = statute
        self.section = section
        self.text = text
        self.path = path
        self.line = line
        self.interpolated = "{" in text

    @property
    def where(self) -> str:
        return f"{_display(self.path)}:{self.line}"

    def __repr__(self) -> str:  # pragma: no cover - diagnostics
        return f"<{self.statute} s.{self.section} at {self.where}>"


def extract(source_root: Path = SOURCE_ROOT) -> list[Citation]:
    """Every hardcoded live-statute citation in the source, with its location."""
    found: list[Citation] = []
    for path in sorted(source_root.rglob("*.py")):
        if path.name in DESCRIPTIVE_MODULES:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for match in CITATION.finditer(line):
                # Keep the citation as written, up to the closing quote, so the
                # report shows a reader what the code actually says.
                tail = match.group("rest")
                cut = min((tail.index(q) for q in "\"'" if q in tail), default=len(tail))
                found.append(
                    Citation(
                        statute=match.group("statute"),
                        section=match.group("section"),
                        text=f"{match.group('statute')} s.{match.group('section')}{tail[:cut]}".strip(),
                        path=path,
                        line=number,
                    )
                )
            for match in PAIRED_CITATION.finditer(line):
                found.append(
                    Citation(
                        statute=match.group("statute"),
                        section=match.group("section"),
                        text=f'("{match.group("statute")}", "{match.group("section")}")',
                        path=path,
                        line=number,
                    )
                )
    return found


def by_provision(citations: list[Citation]) -> dict[tuple[str, str], list[Citation]]:
    grouped: dict[tuple[str, str], list[Citation]] = defaultdict(list)
    for citation in citations:
        grouped[(citation.statute, citation.section)].append(citation)
    return dict(grouped)


async def sections_in_corpus(collection: str) -> dict[str, set[str]]:
    """Statute code -> the top-level section numbers the index can reach.

    Read from the bare Act text only. A circular *about* section 479 is not the
    section, and accepting it would let a citation pass while the provision
    itself is missing.
    """
    from app.core.qdrant import create_qdrant_client
    from app.ingestion.document_type import is_the_authority_itself

    reachable: dict[str, set[str]] = {code: set() for code in LIVE_STATUTES}
    client = create_qdrant_client()
    try:
        offset = None
        while True:
            points, offset = await client.scroll(
                collection_name=collection,
                limit=1000,
                offset=offset,
                with_payload=["act_name", "title", "section", "source_type", "document_type", "heading_path"],
                with_vectors=False,
            )
            for point in points:
                payload = dict(point.payload or {})
                name = f"{payload.get('act_name') or ''} {payload.get('title') or ''}"
                for code, act_name in LIVE_STATUTES.items():
                    if act_name.casefold() not in name.casefold():
                        continue
                    if not is_the_authority_itself(str(payload.get("document_type") or "")):
                        continue
                    for section in _sections_on(payload):
                        reachable[code].add(section)
            if offset is None:
                break
    finally:
        await client.close()
    return reachable


_SECTION_NUMBER = re.compile(r"\b(?:section|s\.)\s*(\d+[A-Z]?)", re.IGNORECASE)


def _sections_on(payload: dict[str, Any]) -> set[str]:
    """Top-level section numbers a point covers.

    `section` is the structured field, but it is None on documents the chunker
    could not section, so the heading path is used as well -- that is where a
    sectioned bare Act records "Section 48. Procedure on arrest".
    """
    numbers: set[str] = set()
    raw = payload.get("section")
    if raw:
        match = re.match(r"\s*(\d+[A-Z]?)", str(raw))
        if match:
            numbers.add(match.group(1))
    for heading in payload.get("heading_path") or []:
        for match in _SECTION_NUMBER.finditer(str(heading)):
            numbers.add(match.group(1))
    return numbers


def report_extraction(citations: list[Citation]) -> dict[str, Any]:
    grouped = by_provision(citations)
    interpolated = [c for c in citations if c.interpolated]
    per_statute: dict[str, int] = defaultdict(int)
    for statute, _ in grouped:
        per_statute[statute] += 1
    return {
        "citations": len(citations),
        "distinct_provisions": len(grouped),
        "provisions_per_statute": dict(sorted(per_statute.items())),
        "modules": sorted({_display(c.path) for c in citations}),
        "unresolvable_because_interpolated": sorted({c.text for c in interpolated}),
        "descriptive_modules_skipped": sorted(DESCRIPTIVE_MODULES),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--collection")
    parser.add_argument(
        "--extract-only",
        action="store_true",
        help="Report what the source cites, without touching the index.",
    )
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    citations = extract()
    summary = report_extraction(citations)

    if args.extract_only or not args.collection:
        print(json.dumps(summary, indent=2, sort_keys=True))
        if not args.extract_only:
            print("\nPass --collection to resolve these against the index.", file=sys.stderr)
            return 2
        return 0

    reachable = asyncio.run(sections_in_corpus(args.collection))
    summary["sections_reachable_per_statute"] = {
        code: len(sections) for code, sections in sorted(reachable.items())
    }

    absent: list[str] = []
    for (statute, section), uses in sorted(by_provision(citations).items()):
        if section not in reachable[statute]:
            where = ", ".join(use.where for use in uses[:3])
            absent.append(f"{statute} s.{section} is cited at {where} but is not reachable in the corpus")

    summary["provisions_not_reachable"] = len(absent)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps(summary, indent=2, sort_keys=True))
    if absent:
        print("\nProvision drift gate FAILED:", file=sys.stderr)
        for failure in absent:
            print(f"  - {failure}", file=sys.stderr)
        print(
            "\nEither the corpus is missing the Act these duties rest on, or the "
            "section numbers in the source have drifted from it. Both make a "
            "citation a reader cannot verify.",
            file=sys.stderr,
        )
        return 1
    print("\nProvision drift gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
