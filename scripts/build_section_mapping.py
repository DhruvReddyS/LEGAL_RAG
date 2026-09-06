#!/usr/bin/env python3
"""Build the section concordance from the official NCRB tables.

The 54 pairs this replaces were authored by a model. They were marked
`pending_legal_review` and were never reviewed, correctly: a reviewer reads
fifty plausible mappings, approves them, and misses the one that is wrong,
because a wrong mapping looks exactly like a right one.

These come from the National Crime Records Bureau, a bureau of the Ministry
of Home Affairs, which publishes the concordance as HTML rather than as a
scan. That matters more than it sounds. The MHA concordance PDF is a
two-page image, and OCR on a dense table of numbers fails silently: a
misread 303 for 308 produces a mapping that is authoritative in appearance
and wrong in substance, which is worse than having none. Nothing here is
OCR'd and nothing is inferred.

Three things the official tables say that the model-authored table could not:

* One provision often replaces many. BNS s.179 stands in for eleven IPC
  sections. Recorded as a single pair that would assert an equivalence the
  Act does not make, so each is its own row and the loader groups them.
* Some provisions were not carried forward at all. Those are recorded with
  no successor rather than omitted -- "this was not re-enacted" is an
  answer, and silence is not.
* "(Change)" marks a provision that was altered, not merely renumbered.
  That is the distinction `ingredients_changed` already existed to carry,
  and it is now populated from the source instead of from judgement.

Usage:
    python scripts/build_section_mapping.py --source <dir of NCRB html>
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "data/legal_kb/metadata/section_mapping.json"

SOURCES = {
    "SectionTableBNS.html": (
        ("BNS", "IPC"),
        "https://www.ncrb.gov.in/uploads/SankalanPortal/SectionTableBNS.html",
    ),
    "SectionTableBNSS.html": (
        ("BNSS", "CrPC"),
        "https://www.ncrb.gov.in/uploads/SankalanPortal/SectionTableBNSS.html",
    ),
    "SectionTableBSA.html": (
        ("BSA", "IEA"),
        "https://www.ncrb.gov.in/uploads/SankalanPortal/SectionTableBSA.html",
    ),
}

# A provision label is a section number, optionally with a sub-section.
# Finding them is the whole parser, and it fails in two directions: too
# strict and CrPC s.41A disappears; too loose and "Explanation to 489A" or
# "within 30 days" become mappings.
_LABEL = re.compile(
    r"(?P<number>\d{1,3}[A-Z]{0,2})\s*"
    r"(?:\((?P<sub>[0-9A-Za-z]{1,3})\))?"
    r"(?=[.(,;]|\s|$)"
)

# What may sit immediately before a label. The tables print labels at the
# start of a cell or after the previous item's terminator -- a full stop, a
# comma, or a parenthetical like "(Change)". A lowercase word before the
# number means it is part of a sentence, not a label: "Explanation to 489A"
# refers to a provision, it does not map one, and "within 30 days" is prose.
_PRECEDED_BY_PROSE = re.compile(r"[A-Za-z]+\s*$")

_CHANGE = re.compile(r"\(\s*change\s*\)", re.I)
_NEW = re.compile(r"\bnew\s+(?:sub-?)?section\b", re.I)
# Whole-cell only. "3. Interpretation-clause. (Definition of "India" -
# Deleted)" deletes a definition inside the clause, not the section, and a
# substring match on "deleted" threw the entire IEA s.3 -> BSA s.2 row away.
_DELETED = re.compile(
    r"^\s*(?:\d{1,3}[A-Z]{0,2}\s*\.?\s*)?(?:deleted|repealed)\s*\.?\s*$", re.I
)
_CHAPTER = re.compile(r"^\s*chapter\b", re.I)


def _cells(row: str) -> list[str]:
    return [
        html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", cell))).strip()
        for cell in re.findall(r"<t[dh].*?</t[dh]>", row, re.S | re.I)
    ]


def _tables(markup: str) -> list[list[list[str]]]:
    out = []
    for table in re.findall(r"<table.*?</table>", markup, re.S | re.I):
        rows = [_cells(r) for r in re.findall(r"<tr.*?</tr>", table, re.S | re.I)]
        out.append([r for r in rows if len(r) >= 2])
    return out


def _labels(cell: str) -> list[str]:
    """Every provision label in a cell, in order.

    "237. Import or export of counterfeit coin. 238. Import or export of
    counterfeits of the Indian coin." yields ["237", "238"] -- both, because
    the replacement genuinely covers both and dropping either would assert a
    narrower correspondence than the table states.
    """
    seen: list[str] = []
    for match in _LABEL.finditer(cell):
        before = cell[: match.start()]
        if before and _PRECEDED_BY_PROSE.search(before):
            continue
        number, sub = match.group("number"), match.group("sub")
        label = f"{number}({sub})" if sub else number
        if label not in seen:
            seen.append(label)
    return seen


def _provision_label(labels: list[str]) -> str:
    """Which of a cell's labels names the provision the row is about.

    The tables print a section header before the provision when the mapping
    is at sub-section level: "303. Theft. 303 (1)". Taking the first label
    records that row against BNS s.303 rather than s.303(1), which is the
    difference between the definition of theft and its punishment -- so a
    question about the punishment gets answered with the definition.

    The rule is the printing convention: among the labels sharing the first
    one's section number, the provision is the last, because the header
    comes first and the specific provision follows the title.
    """
    base = labels[0].split("(")[0]
    same_section = [label for label in labels if label.split("(")[0] == base]
    return same_section[-1]


def _subject(cell: str) -> str:
    """The marginal title, for a human reading the row back."""
    text = _LABEL.sub(" ", cell, count=1).strip(" .")
    text = _CHANGE.sub("", text)
    # Drop the repeated provision label the header form leaves behind, so
    # the subject reads "Theft" rather than "Theft.  303 (1)".
    text = re.sub(r"\s*\d{1,3}[A-Z]{0,2}\s*\(\s*[0-9A-Za-z]{1,3}\s*\)\s*$", "", text)
    return text.strip(" .")[:120]


def _pairs(rows: list[list[str]], new_code: str, old_code: str) -> Iterator[dict]:
    """One row of the table becomes zero or more directed pairs."""
    for cells in rows:
        left, right = cells[0], cells[1]
        if _CHAPTER.match(left) or "-->" in left or "-->" in right:
            continue

        from_labels = _labels(left)
        if not from_labels:
            continue
        from_section = _provision_label(from_labels)
        changed = bool(_CHANGE.search(left) or _CHANGE.search(right))

        if _NEW.search(right):
            # A provision with no predecessor. Nothing to map, and asserting
            # one would invent a lineage the Act does not claim.
            continue
        if _DELETED.match(right):
            # This provision was not carried forward. Recorded rather than
            # dropped: "it was not re-enacted" is an answer, and it is the
            # answer for IPC s.124A, whose supposed successor BNS s.152 is a
            # different offence with different elements.
            yield {
                "from": new_code,
                "from_section": from_section,
                "to": old_code,
                "to_section": None,
                "subject": _subject(left),
                "ingredients_changed": False,
                "status": "no_successor",
            }
            continue
        if _DELETED.match(left):
            continue

        for to_section in _labels(right):
            yield {
                "from": new_code,
                "from_section": from_section,
                "to": old_code,
                "to_section": to_section,
                "subject": _subject(left) or _subject(right),
                "ingredients_changed": changed,
                "status": "mapped",
            }


def build(source_dir: Path) -> dict:
    pairs: list[dict] = []
    provenance: list[str] = []

    for filename, ((new_code, old_code), url) in SOURCES.items():
        path = source_dir / filename
        if not path.is_file():
            raise SystemExit(f"missing {path}; fetch it from {url}")
        tables = _tables(path.read_text(errors="replace"))
        if len(tables) < 2:
            raise SystemExit(f"{filename}: expected two tables, found {len(tables)}")

        # Table 0 is new -> old, table 1 is old -> new. Both are taken from
        # the source; neither is derived from the other. A one-to-many
        # relationship does not invert cleanly, and inferring the reverse is
        # how a mapping acquires a precision the Act never had.
        pairs.extend(_pairs(tables[0], new_code, old_code))
        pairs.extend(_pairs(tables[1], old_code, new_code))
        provenance.append(url)

    # A row can restate a pair; the table is printed for reading, not for
    # parsing. Deduplicate on the directed triple, keeping the first.
    seen: set[tuple] = set()
    unique: list[dict] = []
    for pair in pairs:
        key = (pair["from"], pair["from_section"], pair["to"], pair["to_section"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(pair)

    return {
        "version": 2,
        "created": date.today().isoformat(),
        "provenance": (
            "National Crime Records Bureau (Ministry of Home Affairs) official "
            "section correspondence tables, parsed from the published HTML. "
            "Not OCR'd, not inferred, not model-authored."
        ),
        "source_urls": provenance,
        "review_status": "official_source",
        "notes": [
            "Both directions are read from the source tables. Neither is "
            "derived from the other: one provision frequently replaces "
            "several, and inverting a one-to-many mapping invents a "
            "precision the Act does not have.",
            "'ingredients_changed' comes from the table's own (Change) "
            "marker. Those pairs are the dangerous ones -- a reader who "
            "assumes equivalence gets the elements of the offence wrong.",
            "status 'no_successor' means the provision was not carried "
            "forward. It is recorded rather than omitted, because 'this was "
            "not re-enacted' is an answer and silence is not.",
        ],
        "pairs": unique,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=DESTINATION)
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args()

    payload = build(arguments.source)
    pairs = payload["pairs"]
    from collections import Counter

    directions = Counter((p["from"], p["to"]) for p in pairs)
    print(f"{len(pairs)} pairs")
    for (source, target), count in sorted(directions.items()):
        print(f"  {source:<5} -> {target:<5} {count:>5}")
    print(f"  changed:      {sum(p['ingredients_changed'] for p in pairs):>5}")
    print(f"  no successor: {sum(p['status'] == 'no_successor' for p in pairs):>5}")

    if arguments.dry_run:
        return 0
    arguments.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {arguments.out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
