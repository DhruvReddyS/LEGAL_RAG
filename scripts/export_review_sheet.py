"""Export a sample of real answers for a person to mark, and read the marks back.

Every accuracy figure this project has published so far was judged by its own
verifier. That is a consistency check, not an accuracy measurement: a verifier
and a writer that share a misreading agree with each other. This puts answers in
front of a human reviewer (a law student, a guide or a lawyer) and turns their
marks into the one figure the system cannot grade itself on.

The sample is fixed by a seed and spread across topics, so it is neither chosen
for good answers nor reshuffled until the result looks better.

Usage:
  python scripts/export_review_sheet.py export --answers docs/evidence/answers-v8.json
  python scripts/export_review_sheet.py score --marks review/marks.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "data" / "legal_kb" / "evaluation" / "golden_set_v4.json"
SEED = 20261127
PER_ROLE = {"citizen": 10, "police": 10, "advocate": 10}
REFUSALS = 5
VERDICTS = ("correct", "partly", "wrong")


def _golden() -> dict[str, dict]:
    data = json.loads(GOLDEN.read_text())
    items = data["items"] if isinstance(data, dict) else data
    return {item["id"]: item for item in items}


def _spread(rows: list[dict], count: int, golden: dict[str, dict], rng: random.Random) -> list[dict]:
    """One per topic in turn, so a role's sample is not ten questions on one subject."""
    by_topic: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_topic[str(golden.get(row["id"], {}).get("topic") or "other")].append(row)
    for group in by_topic.values():
        rng.shuffle(group)
    topics = sorted(by_topic)
    rng.shuffle(topics)
    chosen: list[dict] = []
    while len(chosen) < count and any(by_topic.values()):
        for topic in topics:
            if by_topic[topic] and len(chosen) < count:
                chosen.append(by_topic[topic].pop())
    return chosen


def _expected(item: dict) -> str:
    relevant = item.get("relevant") or []
    parts = []
    for entry in relevant:
        if isinstance(entry, dict):
            act = entry.get("act") or entry.get("act_name") or ""
            section = entry.get("section") or ""
            parts.append(f"{act} s.{section}".strip() if section else act)
        else:
            parts.append(str(entry))
    return "; ".join(part for part in parts if part) or "(not listed)"


def export(answers_path: Path, out_dir: Path) -> int:
    data = json.loads(answers_path.read_text())
    golden = _golden()
    rows = [row for row in data["rows"] if row.get("answer")]
    rng = random.Random(SEED)
    sample: list[dict] = []
    for role, count in PER_ROLE.items():
        answered = [row for row in rows if row["role"] == role and row["expectation"] == "answer" and not row["abstained"]]
        sample.extend(_spread(answered, count, golden, rng))
    refused = [row for row in rows if row["expectation"] == "abstain"]
    rng.shuffle(refused)
    sample.extend(refused[:REFUSALS])

    out_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Answer review sheet",
        "",
        f"From `{answers_path.name}`, {len(sample)} answers, sample seed {SEED}.",
        "",
        "## How to mark",
        "For each answer, read the question and the answer, and check them against the law named under",
        "*Expected law* (and any other law you know applies). Then fill in its row in `marks.csv`:",
        "",
        "- **verdict**: `correct` (a lawyer would accept it), `partly` (right core, but a missing or wrong",
        "  detail that matters), or `wrong` (wrong law, wrong rule, or harmful).",
        "- **wrong_citation**: `yes` if a section or Act named is wrong or does not say what is claimed.",
        "- **missing**: the most important thing a correct answer would add, or blank.",
        "- **unsafe**: `yes` if a reader acting on it could be harmed (a wrong deadline, wrong forum, bad advice).",
        "- For a question marked *should refuse*, `correct` means it rightly declined or stayed in scope.",
        "",
        "The system does not know which answers are in this sample, and nothing here was edited.",
        "",
    ]
    marks = [("number", "id", "role", "verdict", "wrong_citation", "missing", "unsafe", "notes")]
    for number, row in enumerate(sample, 1):
        item = golden.get(row["id"], {})
        kind = "should refuse" if row["expectation"] == "abstain" else row["role"]
        lines += [
            f"## {number}. {kind}: `{row['id']}`",
            "",
            f"**Question:** {item.get('question', '(question not found)')}",
            "",
            f"**Expected law:** {_expected(item) if row['expectation'] == 'answer' else 'none; outside what the corpus covers'}",
            "",
            "**Answer as shown to the user:**",
            "",
            *[f"> {line}" if line else ">" for line in row["answer"].strip().splitlines()],
            "",
        ]
        marks.append((str(number), row["id"], kind, "", "", "", "", ""))

    (out_dir / "review-sheet.md").write_text("\n".join(lines))
    with (out_dir / "marks.csv").open("w", newline="") as handle:
        csv.writer(handle).writerows(marks)
    print(f"wrote {out_dir / 'review-sheet.md'} and {out_dir / 'marks.csv'} ({len(sample)} answers)")
    return 0


def score(marks_path: Path) -> int:
    with marks_path.open() as handle:
        rows = [row for row in csv.DictReader(handle)]
    marked = [row for row in rows if row["verdict"].strip().lower() in VERDICTS]
    if len(marked) < len(rows):
        print(f"{len(rows) - len(marked)} of {len(rows)} rows have no valid verdict yet", file=sys.stderr)
    if not marked:
        return 1
    overall = Counter(row["verdict"].strip().lower() for row in marked)
    print(f"marked {len(marked)}: " + ", ".join(f"{verdict} {overall[verdict]}" for verdict in VERDICTS))
    print(f"correct {overall['correct'] / len(marked):.0%}, correct or partly {(overall['correct'] + overall['partly']) / len(marked):.0%}")
    for flag in ("wrong_citation", "unsafe"):
        flagged = sum(row[flag].strip().lower() == "yes" for row in marked)
        print(f"{flag}: {flagged} of {len(marked)}")
    by_role: dict[str, Counter] = defaultdict(Counter)
    for row in marked:
        by_role[row["role"]][row["verdict"].strip().lower()] += 1
    for role, counts in sorted(by_role.items()):
        total = sum(counts.values())
        print(f"  {role:14} correct {counts['correct']}/{total}, partly {counts['partly']}, wrong {counts['wrong']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    exporting = commands.add_parser("export")
    exporting.add_argument("--answers", type=Path, required=True)
    exporting.add_argument("--out", type=Path, default=ROOT / "review")
    scoring = commands.add_parser("score")
    scoring.add_argument("--marks", type=Path, required=True)
    args = parser.parse_args()
    return export(args.answers, args.out) if args.command == "export" else score(args.marks)


if __name__ == "__main__":
    raise SystemExit(main())
