#!/usr/bin/env python3
"""Does the parser find the sections each major Act actually has?

Retrieval, citations and the concordance all trust the section label, and a wrong
label is invisible: the text still comes back, under another number. This parses
the cached extracted text and compares against each Act's known range, then spot
checks that named sections hold the words they should.

Run before spending hours on a rebuild. Exits 1 on any failed spot check.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.ingestion.classifier import LegalDocumentType  # noqa: E402
from app.ingestion.extract import ExtractedDocument  # noqa: E402
from app.ingestion.structure import parse_legal_structure  # noqa: E402

KB = ROOT / "data" / "legal_kb"

# Title prefix -> highest section number. Coverage is of numbers 1..N, and a repealed
# or omitted section legitimately has no head, so 100% is not expected of old Acts.
EXPECTED = {
    "THE BHARATIYA NYAYA SANHITA, 2023": 358,
    "THE BHARATIYA NAGARIK SURAKSHA SANHITA, 2023": 531,
    "THE BHARATIYA SAKSHYA ADHINIYAM, 2023": 170,
    "The Indian Penal Code Act, 1860": 511,
    "The Indian Contract Act, 1872": 266,
    "The Code of Civil Procedure, 1908": 158,
    "The Transfer of Property Act, 1882": 137,
    "Consumer Protection Act, 2019": 107,
    "Motor Vehicles Act, 1988": 217,
    "The Hindu Marriage Act, 1955": 30,
    "The Protection of Women from Domestic Violence Act, 2005": 37,
    "The Right to Information Act, 2005": 31,
    "The Limitation Act, 1963": 32,
    "The Juvenile Justice (Care and Protection of Children) Act, 2015": 112,
    "The Protection of Children from Sexual Offences Act, 2012": 46,
}

# Title prefix, section, words that must appear in that section's text.
SPOT_CHECKS = (
    ("THE BHARATIYA NYAYA SANHITA, 2023", "303", "theft"),
    ("THE BHARATIYA NAGARIK SURAKSHA SANHITA, 2023", "35", "arrest"),
    ("THE BHARATIYA NAGARIK SURAKSHA SANHITA, 2023", "173", "cognizable"),
    ("THE BHARATIYA NAGARIK SURAKSHA SANHITA, 2023", "187", "custody"),
    ("THE BHARATIYA NAGARIK SURAKSHA SANHITA, 2023", "192", "diary"),
    ("THE BHARATIYA NAGARIK SURAKSHA SANHITA, 2023", "482", "bail"),
    ("THE BHARATIYA SAKSHYA ADHINIYAM, 2023", "26", "dead"),
    ("The Indian Penal Code Act, 1860", "34", "common intention"),
    ("The Indian Penal Code Act, 1860", "378", "dishonestly"),
    ("The Indian Contract Act, 1872", "13", "consent"),
    ("The Indian Contract Act, 1872", "15", "coercion"),
    ("Motor Vehicles Act, 1988", "166", "compensation"),
    ("The Right to Information Act, 2005", "6", "information"),
)


def load_units(row: dict) -> list:
    path = KB / "processed" / "extracted_text" / f"{row['canonical_document_id']}.json"
    document = ExtractedDocument.model_validate_json(path.read_text(encoding="utf-8"))
    return parse_legal_structure(document, LegalDocumentType.ACT)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, help="also write the result here")
    args = parser.parse_args()

    rows = [json.loads(line) for line in (KB / "metadata" / "canonical_documents.jsonl").open(encoding="utf-8")]
    by_title: dict[str, dict] = {}
    for row in rows:
        title = str(row.get("title") or "")
        for prefix in EXPECTED:
            if title.startswith(prefix) and prefix not in by_title:
                by_title[prefix] = row

    report: dict[str, dict] = {}
    units_by_title: dict[str, list] = {}
    print(f"{'Act':<66}{'found':>6}{'of':>6}{'false':>7}")
    for prefix, top in EXPECTED.items():
        if prefix not in by_title:
            print(f"{prefix[:64]:<66}  not in manifest")
            continue
        units = load_units(by_title[prefix])
        units_by_title[prefix] = units
        labels = {str(unit.section) for unit in units if unit.section}
        numbers = {int(match.group(1)) for label in labels if (match := re.match(r"(\d+)", label))}
        found = len({number for number in numbers if 1 <= number <= top})
        false = len({number for number in numbers if number > top})
        report[prefix] = {"found": found, "expected": top, "beyond_range": false}
        print(f"{prefix[:64]:<66}{found:>6}{top:>6}{false:>7}")

    failed = []
    print("\nSpot checks")
    for prefix, section, words in SPOT_CHECKS:
        units = units_by_title.get(prefix, [])
        text = " ".join(unit.text for unit in units if str(unit.section) == section)
        passed = words.casefold() in re.sub(r"\s+", " ", text).casefold()
        print(f"  {'ok  ' if passed else 'FAIL'} {prefix[:48]:<50} s.{section:<5} {words}")
        if not passed:
            failed.append(f"{prefix} s.{section}")

    if args.json:
        args.json.write_text(json.dumps({"coverage": report, "failed": failed}, indent=2), encoding="utf-8")
    if failed:
        print(f"\n{len(failed)} spot checks failed")
        return 1
    print("\nAll spot checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
