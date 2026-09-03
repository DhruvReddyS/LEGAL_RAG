#!/usr/bin/env python3
"""Strip download-page artefacts from corpus titles.

Titles were captured from government listing pages, so 40 of them carry the
page's file furniture rather than the document's name:

    The Code of Criminal Procedure, 1973 (Act No.2 of 1974) 1996
    Accessible_Vol_01(PDF 4.15MB) | Accessible_Vol_02(PDF 3.42MB)

That string is what a citizen sees under every citation from those documents,
and it makes a correct answer look untrustworthy.

The repair is deliberately conservative: it removes only file-listing patterns
and never rewrites a title's substance. A title that survives unchanged is left
alone. Genuinely long official titles are not truncated - "Advisory on measures
to be taken by States/UTs to curb misuse of section 498-A IPC" is the document's
real name, and shortening it would lose meaning.

Run with --apply to write the manifest and update the matching Qdrant payloads.
Without it, prints the diff and changes nothing.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

MANIFEST = (
    Path(__file__).resolve().parents[1]
    / "data" / "legal_kb" / "metadata" / "canonical_documents.jsonl"
)

# Each pattern targets one artefact of a download listing, not prose.
_ARTEFACTS = (
    # "Accessible_Vol_01(PDF 4.15MB) | Accessible_Hindi(PDF 7.86MB)"
    re.compile(r"\s*\|?\s*Accessible[_ ][^|]*?\((?:PDF\s*)?[\d.]+\s*(?:MB|KB)\)", re.I),
    # "Accessible_Part_1( 6.81MB)" and bare "Accessible_Part_2"
    re.compile(r"\s*\|?\s*Accessible[_ ]Part[_ ]?\d*\s*\(?\s*[\d.]*\s*(?:MB|KB)?\s*\)?", re.I),
    # A trailing size with no label at all.
    re.compile(r"\s*\(\s*(?:PDF\s*)?[\d.]+\s*(?:MB|KB)\s*\)", re.I),
    # A stray filename.
    re.compile(r"\s*\b[\w-]+\.pdf\b", re.I),
)



def clean_title(title: str) -> str:
    cleaned = title
    for pattern in _ARTEFACTS:
        cleaned = pattern.sub("", cleaned)
    cleaned = cleaned.strip(" |,-–—\t")
    cleaned = " ".join(cleaned.split())
    # A trailing year is deliberately left alone. An earlier version stripped
    # one when the title named another year elsewhere, which turned
    # "Transgender Persons (Protection of Rights) Rules, 2020" into "Rules" and
    # "(Prevention of Atrocities) Act, 1989" into "Act" - far worse than the
    # artefact being removed. In Indian legal titles the year is the title.
    return cleaned or title


def load() -> list[dict]:
    return [
        json.loads(line)
        for line in MANIFEST.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


async def update_qdrant(changes: dict[str, str]) -> int:
    """Set the new title on every point of each repaired document."""
    from qdrant_client import models

    from app.core.qdrant import create_qdrant_client
    from app.ingestion.init_qdrant import GLOBAL_LEGAL_CORPUS

    client = create_qdrant_client()
    updated = 0
    try:
        for canonical_id, title in changes.items():
            await client.set_payload(
                collection_name=GLOBAL_LEGAL_CORPUS,
                payload={"title": title},
                points=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="canonical_document_id",
                            match=models.MatchValue(value=canonical_id),
                        )
                    ]
                ),
                wait=True,
            )
            updated += 1
    finally:
        await client.close()
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the manifest and Qdrant")
    arguments = parser.parse_args()

    documents = load()
    changes: dict[str, str] = {}
    for document in documents:
        original = document.get("title") or ""
        cleaned = clean_title(original)
        if cleaned != original:
            changes[document["canonical_document_id"]] = cleaned
            document["title"] = cleaned

    print(f"{len(changes)} of {len(documents)} titles need repair\n")
    for index, (canonical_id, title) in enumerate(list(changes.items())[:12], 1):
        original = next(
            d for d in load() if d["canonical_document_id"] == canonical_id
        )["title"]
        print(f"{index:>3}. before: {original[:104]}")
        print(f"     after : {title[:104]}\n")

    if not arguments.apply:
        print("dry run; pass --apply to write")
        return 0

    MANIFEST.write_text(
        "\n".join(json.dumps(d, ensure_ascii=False) for d in documents) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {MANIFEST}")
    try:
        updated = asyncio.run(update_qdrant(changes))
        print(f"updated payloads for {updated} documents in Qdrant")
    except Exception as exc:  # noqa: BLE001
        print(f"Qdrant not updated ({type(exc).__name__}); re-run --apply with it up")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
