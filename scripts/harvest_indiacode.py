#!/usr/bin/env python3
"""Resolve Act titles to India Code PDFs and write a source manifest.

The India Code library moved to indiacode.gov.in, which runs DSpace 7 and
exposes a REST API. The old indiacode.nic.in is unreachable from here - curl
times out on every handle and the browser gets an Akamai edge error - so this
is the only route to the central Act texts, and it is a far better one: the
metadata carries the Act number, the year of enactment, the administering
ministry and a repealed flag.

    python scripts/harvest_indiacode.py --titles acts.txt --out batch.json
    python scripts/harvest_indiacode.py --titles acts.txt --jurisdiction AP

One line per wanted Act in the titles file. Resolution is reported per line so
a title that matched nothing, or matched something suspicious, is visible
rather than silently absent.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://indiacode.gov.in/server/api"
AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
         "(KHTML, like Gecko) Version/18.0 Safari/605.1.15")
DELAY_SECONDS = 1.2

# act_id encodes the jurisdiction: AC_CEN_ for a central Act, a state code
# otherwise. There is no facet for this, so it is read off the identifier.
PREFIX = {"CEN": "AC_CEN_", "AP": "AC_AP_", "TG": "AC_TG_", "TS": "AC_TG_"}

# Each jurisdiction is a DSpace community. Without scoping to one, a search for
# the Minimum Wages Act returns Haryana's, Punjab's and Jharkhand's adaptations
# ahead of the central Act, and the central one falls off the page.
COMMUNITY = {
    "CEN": "f467b316-98f0-4c08-a722-a2627e45bc19",
    "AP": "bd41570a-ba81-4bef-987c-20a1cda1689f",
    "TG": "63a13e3c-4624-41c4-b765-a3dc8cec7315",
    "TS": "63a13e3c-4624-41c4-b765-a3dc8cec7315",
}


def meta(item: dict, key: str) -> str | None:
    values = (item.get("metadata") or {}).get(key)
    return values[0]["value"] if values else None


def search(session: requests.Session, phrase: str, scope: str,
           size: int = 100, page: int = 0) -> list[dict]:
    params = {"f.identifier_collection": "ACT,equals", "scope": scope,
              "page": page, "size": size}
    if phrase:
        params["query"] = phrase
    response = session.get(f"{BASE}/discover/search/objects", timeout=(10, 90), params=params)
    response.raise_for_status()
    found = response.json().get("_embedded", {}).get("searchResult", {})
    return [o.get("_embedded", {}).get("indexableObject", {})
            for o in found.get("_embedded", {}).get("objects", [])]


def pdf_for(session: requests.Session, uuid: str) -> tuple[str, str] | None:
    """The ORIGINAL bundle's first PDF, as (filename, download url)."""
    bundles = session.get(f"{BASE}/core/items/{uuid}/bundles", timeout=(10, 60))
    bundles.raise_for_status()
    original = next((b for b in bundles.json().get("_embedded", {}).get("bundles", [])
                     if b.get("name") == "ORIGINAL"), None)
    if not original:
        return None
    listing = session.get(f"{BASE}/core/bundles/{original['uuid']}/bitstreams",
                          timeout=(10, 60), params={"page": 0, "size": 50})
    listing.raise_for_status()
    for bitstream in listing.json().get("_embedded", {}).get("bitstreams", []):
        name = bitstream.get("name") or ""
        if name.lower().endswith(".pdf"):
            return name, f"{BASE}/core/bitstreams/{bitstream['uuid']}/content"
    return None


NOISE = {"the", "act", "of", "and", "or", "a", "an", "to", "for"}

def _words(text: str) -> set[str]:
    return {w for w in re.sub(r"[^a-z0-9 ]", " ", text.lower()).split()
            if w and w not in NOISE and not w.isdigit()}


def score(wanted: str, candidate: str) -> float:
    """Overlap between what was asked for and a result, as a ratio.

    Counting shared words alone picked "The Industrial Disputes (Banking and
    Insurance Companies) Act, 1949" for "Banking Regulation Act 1949", because
    it shares two words and the extra words cost it nothing. A ratio over the
    union penalises a candidate that says much more than was asked.
    """
    want, got = _words(wanted), _words(candidate)
    if not want or not got:
        return 0.0
    return len(want & got) / len(want | got)


def year_of(text: str) -> str | None:
    found = re.findall(r"\b(1[6-9]\d{2}|20\d{2})\b", text)
    return found[-1] if found else None


def slugify(title: str) -> str:
    s = re.sub(r"^the\s+", "", title.lower())
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:70]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--titles", type=Path,
                        help="one wanted Act per line, optionally 'title | search phrase'")
    parser.add_argument("--enumerate", type=int, metavar="N",
                        help="instead of resolving titles, take the first N Acts of the jurisdiction")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--jurisdiction", default="CEN", choices=sorted(PREFIX))
    args = parser.parse_args()

    prefix = PREFIX[args.jurisdiction]
    place = {"CEN": "India - Central", "AP": "India - Andhra Pradesh",
             "TG": "India - Telangana", "TS": "India - Telangana"}[args.jurisdiction]

    session = requests.Session()
    session.headers.update({"User-Agent": AGENT, "Accept": "application/json"})

    if args.enumerate:
        wanted = []
        for page in range((args.enumerate // 100) + 1):
            if len(wanted) >= args.enumerate:
                break
            time.sleep(DELAY_SECONDS)
            batch = search(session, "", COMMUNITY[args.jurisdiction], size=100, page=page)
            if not batch:
                break
            for item in batch:
                name = (item.get("name") or "").strip()
                if name and len(wanted) < args.enumerate:
                    wanted.append((name, name))
        print(f"enumerated {len(wanted)} {args.jurisdiction} Acts")
    else:
        wanted = []
        for line in args.titles.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            phrase, _, alias = line.partition("|")
            wanted.append((phrase.strip(), alias.strip() or phrase.strip()))

    rows, unresolved = [], []
    seen_files: set[str] = set()

    for phrase, lookup in wanted:
        time.sleep(DELAY_SECONDS)
        try:
            results = search(session, lookup, COMMUNITY[args.jurisdiction])
        except requests.RequestException as error:
            unresolved.append((phrase, f"search failed: {type(error).__name__}"))
            continue
        in_scope = [r for r in results
                    if (meta(r, "dc.identifier.act_id") or "").startswith(prefix)]
        if not in_scope:
            unresolved.append((phrase, f"no {args.jurisdiction} Act among {len(results)} results"))
            continue
        # When the wanted title names a year, the Act's own year must equal it.
        # Without that, a search for the Banking Regulation Act, 1949 happily
        # returns a different 1949 Act about banking.
        asked_year = year_of(lookup)
        if asked_year:
            dated = [r for r in in_scope if (meta(r, "dc.date.act_year") or "") == asked_year]
            if not dated:
                unresolved.append((phrase, f"no {args.jurisdiction} Act of {asked_year} among {len(in_scope)} results"))
                continue
            in_scope = dated
        best = max(in_scope, key=lambda r: score(lookup, r.get("name") or ""))
        overlap = score(lookup, best.get("name") or "")
        if overlap < 0.6:
            unresolved.append((phrase, f"best match only {overlap:.2f}: {str(best.get('name'))[:52]!r}"))
            continue
        try:
            found = pdf_for(session, best["uuid"])
        except requests.RequestException as error:
            unresolved.append((phrase, f"bitstream lookup failed: {type(error).__name__}"))
            continue
        if not found:
            unresolved.append((phrase, "item carries no PDF"))
            continue
        _, url = found
        title = (best.get("name") or phrase).strip().rstrip(".")
        repealed = (meta(best, "dc.identifier.repealed") or "").lower() == "true"
        year = meta(best, "dc.date.act_year")
        number = meta(best, "dc.identifier.act_number")
        ministry = meta(best, "dc.identifier.ministry_name") or ""
        slug = slugify(title)
        filename = f"{args.jurisdiction.lower()}__indiacode__act__{slug}__en.pdf"
        if filename in seen_files:
            filename = f"{args.jurisdiction.lower()}__indiacode__act__{slug}-{number or 'x'}__en.pdf"
        seen_files.add(filename)
        rows.append({
            "id": slug, "title": title + (" (repealed)" if repealed else ""),
            "domain": "central_act", "document_type": "act",
            "authority": ("Government of India" if args.jurisdiction == "CEN"
                          else f"Government of {place.split(' - ')[1]}"),
            "jurisdiction": place, "language": "English",
            "legal_status": "REPEALED" if repealed else "CURRENT_REVIEW_REQUIRED",
            "current_as_of": "2026-10-03", "format": "pdf",
            "filename": filename, "url": url,
            "currency_note": (
                f"India Code records this as Act {number or '?'} of {year or '?'}"
                + (f", administered by {ministry.title()}" if ministry and ministry != "NO MINISTRY" else "")
                + (". India Code marks it repealed." if repealed
                   else ". India Code does not mark it repealed, which is evidence of currency but not of the latest amendment.")),
        })
        print(f"  ok    {title[:66]}")

    args.out.write_text(json.dumps(rows, indent=1) + "\n")
    print(f"\n{len(rows)} resolved -> {args.out}")
    if unresolved:
        print(f"{len(unresolved)} unresolved:")
        for phrase, why in unresolved:
            print(f"  --    {phrase[:46]:48} {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
