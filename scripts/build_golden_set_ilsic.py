#!/usr/bin/env python3
"""Build an external retrieval test set from ILSIC's layperson test split.

ILSIC ("Corpora for Identifying Indian Legal Statutes from Queries by Laymen",
EACL 2026, MIT licence, https://github.com/Law-AI/ilsic) pairs real questions
from Indian legal-advice forums with the sections the answering lawyers cited.
It is used here as an outside check on the in-house golden set: the questions
were not written by us and the labels were not chosen to suit Corpusil.

What this script does, and why:
- Old criminal codes are converted to the new ones (IPC -> BNS, CrPC -> BNSS,
  IEA -> BSA) with the NCRB correspondence table in
  data/legal_kb/metadata/section_mapping.json. A one-to-many mapping keeps every
  target, so any of them counts. Sections with no equivalent (IPC 497,
  adultery, struck down) are dropped.
- Every remaining (Act, section) is checked to exist in the collection. A label
  the corpus cannot return would only measure coverage, not retrieval.
- A question is kept only if *all* of its labels survive. Dropping some labels
  and keeping the question would make it easier than the source intended.
- Consumer Protection Act, 1986 is excluded: it was repealed by the 2019 Act and
  the section numbers do not carry over.

The ILSIC data itself is not committed. Download FT-Layman-test.jsonl.xz from the
dataset's Google Drive folder, unpack it, and pass its path.

Usage:
    python scripts/build_golden_set_ilsic.py --ilsic path/to/FT-Layman-test.jsonl \
        --collection global_legal_corpus_v6 --sample 100
"""

from __future__ import annotations

import argparse
import collections
import json
import random
import re
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAPPING = ROOT / "data" / "legal_kb" / "metadata" / "section_mapping.json"
OUT = ROOT / "data" / "legal_kb" / "evaluation" / "golden_set_ilsic_v1.json"

OLD_CODES = {
    "The Indian Penal Code, 1860": ("IPC", "nyaya sanhita"),
    "The Code of Criminal Procedure, 1973": ("CrPC", "nagarik suraksha"),
    "The Indian Evidence Act, 1872": ("IEA", "sakshya adhiniyam"),
}
NEW_CODE_KEY = {"BNS": "nyaya sanhita", "BNSS": "nagarik suraksha", "BSA": "sakshya adhiniyam"}

# ILSIC Act name -> the substring the scorer matches against act_name/title.
# Several Acts appear in the corpus under more than one spelling ("Transfer
# Property 1882"), so a list of alternatives is allowed.
CIVIL_ACTS = {
    "Constitution of India": ["constitution of india"],
    "The Hindu Marriage Act, 1955": ["hindu marriage act"],
    "The Protection of Women from Domestic Violence Act, 2005": ["domestic violence act"],
    "The Negotiable Instruments Act, 1881": ["negotiable instruments act"],
    "The Indian Contract Act, 1872": ["indian contract act"],
    "The Transfer Of Property Act, 1882": ["transfer of property act", "transfer property 1882"],
    "The Code of Civil Procedure, 1908": ["code of civil procedure"],
    "The Hindu Succession Act, 1956": ["hindu succession act"],
    "The Registration Act, 1908": ["registration act, 1908", "registration 1908"],
    "The Indian Easements Act, 1882": ["easements act"],
    "The Specific Relief Act, 1963": ["specific relief act"],
    "The Dowry Prohibition Act, 1961": ["dowry prohibition act"],
    "The Family Courts Act, 1984": ["family courts act"],
    "Real Estate (Regulation And Development) Act, 2016": ["real estate (regulation and development) act"],
    "The Hindu Adoptions And Maintenance Act, 1956": ["hindu adoptions and maintenance act"],
    "The Securitisation And Reconstruction Of Financial Assets And Enforcement Of Security Interest Act, 2002": ["securitisation and reconstruction"],
    "The Passports Act, 1967": ["passports act"],
    "The Motor Vehicles Act, 1988": ["motor vehicles act"],
    "The Information Technology Act, 2000": ["information technology act, 2000"],
    "The Right to Information Act, 2005": ["right to information act"],
    "The Indian Succession Act, 1925": ["indian succession act"],
    "The Guardians And Wards Act, 1890": ["guardians and wards act"],
}

LABEL = re.compile(r"(?:Section|Article)\s+(\S+)\s+of\s+(.+)", re.IGNORECASE)


def base_section(section: str) -> str:
    """'318(4)' -> '318', '21A' stays '21A'. The corpus indexes whole sections."""
    return re.split(r"[\s(]", section.strip(), maxsplit=1)[0].upper().rstrip(".")


def corpus_index(qdrant: str, collection: str) -> set[tuple[str, str]]:
    """Every (act_name + title, section) pair in the collection, casefolded."""
    seen: set[tuple[str, str]] = set()
    offset = None
    while True:
        body = {"limit": 5000, "with_payload": ["act_name", "title", "section"], "with_vector": False}
        if offset is not None:
            body["offset"] = offset
        request = urllib.request.Request(
            f"{qdrant}/collections/{collection}/points/scroll",
            data=json.dumps(body).encode(),
            headers={"content-type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.load(response)["result"]
        for point in result["points"]:
            payload = point.get("payload") or {}
            section = str(payload.get("section") or "").casefold().strip()
            if section:
                haystack = f"{payload.get('act_name') or ''} {payload.get('title') or ''}".casefold()
                seen.add((haystack, section))
        offset = result.get("next_page_offset")
        if offset is None:
            return seen


def exists(index_by_section: dict[str, list[str]], act_key: str, section: str) -> bool:
    return any(act_key in haystack for haystack in index_by_section.get(section.casefold(), ()))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ilsic", type=Path, required=True)
    parser.add_argument("--collection", default="global_legal_corpus_v6")
    parser.add_argument("--qdrant", default="http://localhost:6333")
    parser.add_argument("--sample", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20261127)
    parser.add_argument("--out", type=Path, default=OUT)
    arguments = parser.parse_args()

    mapping: dict[tuple[str, str], set[tuple[str, str]]] = collections.defaultdict(set)
    for pair in json.loads(MAPPING.read_text(encoding="utf-8"))["pairs"]:
        if pair["from"] in ("IPC", "CrPC", "IEA") and pair["status"] == "mapped":
            mapping[(pair["from"], base_section(pair["from_section"]))].add(
                (NEW_CODE_KEY[pair["to"]], base_section(pair["to_section"]))
            )

    index_by_section: dict[str, list[str]] = collections.defaultdict(list)
    for haystack, section in corpus_index(arguments.qdrant, arguments.collection):
        index_by_section[section].append(haystack)

    rows = [json.loads(line) for line in arguments.ilsic.read_text(encoding="utf-8").splitlines() if line.strip()]
    drop = collections.Counter()
    kept: list[dict] = []
    for number, row in enumerate(rows, start=1):
        sources: list[dict[str, str]] = []
        criminal = False
        ok = True
        for label in row["answer"]:
            match = LABEL.match(label)
            if not match:
                drop["label not a section"] += 1
                ok = False
                break
            section, act = base_section(match.group(1)), match.group(2).strip()
            if act in OLD_CODES:
                code, _ = OLD_CODES[act]
                targets = [t for t in mapping.get((code, section), ()) if exists(index_by_section, *t)]
                if not targets:
                    drop[f"{code} s.{section} has no new-code section in the corpus"] += 1
                    ok = False
                    break
                sources += [{"act": key, "section": sec} for key, sec in sorted(targets)]
                criminal = True
            elif act in CIVIL_ACTS:
                keys = [k for k in CIVIL_ACTS[act] if exists(index_by_section, k, section)]
                if not keys:
                    drop[f"{act} s.{section} not in the corpus"] += 1
                    ok = False
                    break
                sources += [{"act": key, "section": section} for key in keys]
            else:
                drop[f"Act not covered: {act}"] += 1
                ok = False
                break
        if not ok:
            continue
        unique = [dict(s) for s in {tuple(sorted(s.items())) for s in sources}]
        kept.append(
            {
                "id": f"ilsic-lay-test-{number:03d}",
                "question": row["instruction"].strip(),
                "role": "citizen",
                "topic": "criminal" if criminal else "civil",
                "expectation": "answer",
                "relevant": sorted(unique, key=lambda s: (s["act"], s["section"])),
                "note": "ILSIC labels: " + "; ".join(row["answer"]),
            }
        )

    # Half criminal, half civil where possible, so neither dominates the score.
    rng = random.Random(arguments.seed)
    criminal = [k for k in kept if k["topic"] == "criminal"]
    civil = [k for k in kept if k["topic"] == "civil"]
    rng.shuffle(criminal)
    rng.shuffle(civil)
    half = arguments.sample // 2
    take_civil = min(len(civil), half)
    sample = civil[:take_civil] + criminal[: arguments.sample - take_civil]
    sample.sort(key=lambda k: k["id"])

    arguments.out.write_text(
        json.dumps(
            {
                "version": "ilsic-v1",
                "created": date.today().isoformat(),
                "notes": [
                    "External test set: questions and labels from ILSIC (EACL 2026, MIT licence), "
                    "layperson test split. Built by scripts/build_golden_set_ilsic.py; not tuned to Corpusil.",
                    "Labels are the sections forum lawyers cited, extracted by the ILSIC authors with an LLM. "
                    "They are often incomplete, so precision and citation accuracy understate quality; "
                    "Recall@k is the fair measure.",
                    "IPC/CrPC/IEA labels converted to BNS/BNSS/BSA with the NCRB table; one-to-many "
                    "conversions accept any target. Every source was checked to exist in the collection.",
                    f"Kept {len(kept)} of {len(rows)} test questions; sampled {len(sample)} "
                    f"({take_civil} civil, {len(sample) - take_civil} criminal), seed {arguments.seed}.",
                ],
                "items": sample,
            },
            indent=1,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"kept {len(kept)} of {len(rows)}; criminal {len(criminal)}, civil {len(civil)}")
    print(f"wrote {len(sample)} items to {arguments.out}")
    for reason, count in drop.most_common(15):
        print(f"  dropped {count:4}  {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
