#!/usr/bin/env python3
"""Download a source manifest into candidate_imports, politely and resumably.

Acquisition is the fragile half of corpus work: government hosts rate-limit,
time out, and sometimes answer an HTML error page with a 200. This downloads a
source JSON written by hand or by browser discovery, skips what is already on
disk, and records every refusal in a queue instead of losing it.

    python scripts/fetch_sources.py data/source_materials/<batch>.json
    python scripts/fetch_sources.py <batch>.json --retry-failed

Exit status is zero even when some downloads fail; the queue is the record.
"""
from __future__ import annotations

import argparse, json, sys, time
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "data/source_materials/candidate_imports"
FAILED = ROOT / "data/legal_kb/metadata/failed_downloads.jsonl"

# A browser user agent: several of these hosts answer a bare python-requests
# agent with a block page, and the content is public either way.
AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
         "(KHTML, like Gecko) Version/18.0 Safari/605.1.15")
# Per-host courtesy delay. One request at a time per host, spaced.
HOST_DELAY_SECONDS = 2.5
MIN_PDF_BYTES = 20_000


def load_failed() -> dict[str, dict]:
    if not FAILED.exists():
        return {}
    rows = {}
    for line in FAILED.read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["url"]] = row
    return rows


def fetch(session: requests.Session, url: str, target: Path,
          attempts: int = 3) -> tuple[bool, str]:
    # These hosts drop long transfers part-way through and report a complete
    # Content-Length, so a truncated body looks like a hard failure on the
    # first try and succeeds on the second. Retry before giving up.
    for attempt in range(1, attempts + 1):
        good, detail = _fetch_once(session, url, target)
        if good or attempt == attempts:
            return good, detail
        time.sleep(HOST_DELAY_SECONDS * attempt)
    raise AssertionError("unreachable")


def _fetch_once(session: requests.Session, url: str, target: Path) -> tuple[bool, str]:
    try:
        response = session.get(url, timeout=(15, 300), allow_redirects=True)
    except requests.RequestException as error:
        return False, f"{type(error).__name__}: {error}"
    if response.status_code != 200:
        return False, f"HTTP {response.status_code}"
    body = response.content
    kind = response.headers.get("content-type", "")
    # A PDF that is really an HTML error page is worse than a failure: it would
    # be promoted and indexed as law.
    if target.suffix.lower() == ".pdf":
        if not body.startswith(b"%PDF"):
            return False, f"not a PDF (content-type {kind!r}, {len(body)} bytes)"
        # A valid PDF that is merely short is a one-page circular, not a
        # failure. Whether it carries enough text to index is promotion's
        # decision, which reads the pages rather than the byte count.
        if len(body) < MIN_PDF_BYTES:
            target.write_bytes(body)
            return True, f"{len(body)} bytes, short - promotion will check it"
    target.write_bytes(body)
    return True, f"{len(body) // 1024} KB"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--retry-failed", action="store_true",
                        help="attempt URLs already recorded as failures")
    args = parser.parse_args()

    sources = json.loads(args.manifest.read_text())

    # A slug truncated to a fixed width can collide, and two Acts sharing a
    # filename means the second overwrites the first and never reaches the
    # index. Refuse the manifest rather than lose a document quietly.
    seen: dict[str, str] = {}
    clashes = []
    for source in sources:
        earlier = seen.get(source["filename"])
        if earlier:
            clashes.append(f"  {source['filename']}\n    {earlier}\n    {source['title']}")
        seen[source["filename"]] = source.get("title") or source["url"]
    if clashes:
        print("refusing this manifest, these entries share a filename:")
        print("\n".join(clashes))
        return 1
    DEST.mkdir(parents=True, exist_ok=True)
    known_failures = load_failed()

    session = requests.Session()
    session.headers["User-Agent"] = AGENT
    session.headers["Accept"] = "application/pdf,text/html;q=0.9,*/*;q=0.8"

    last_hit: dict[str, float] = {}
    ok = skipped = failed = 0
    records = []

    for source in sources:
        target = DEST / source["filename"]
        if target.exists() and target.stat().st_size >= MIN_PDF_BYTES:
            print(f"  have  {source['filename']}")
            skipped += 1
            continue
        if not args.retry_failed and source["url"] in known_failures:
            print(f"  queued {source['filename']}  (known failure, use --retry-failed)")
            skipped += 1
            continue

        host = urlparse(source["url"]).netloc
        wait = HOST_DELAY_SECONDS - (time.monotonic() - last_hit.get(host, 0.0))
        if wait > 0:
            time.sleep(wait)
        last_hit[host] = time.monotonic()

        good, detail = fetch(session, source["url"], target)
        if good:
            print(f"  ok    {source['filename']}  {detail}")
            ok += 1
        else:
            print(f"  FAIL  {source['filename']}  {detail}")
            failed += 1
            records.append({"id": source.get("id"), "title": source.get("title"),
                            "url": source["url"], "filename": source["filename"],
                            "reason": detail, "attempted": time.strftime("%Y-%m-%dT%H:%M:%S")})

    if records:
        FAILED.parent.mkdir(parents=True, exist_ok=True)
        with FAILED.open("a") as handle:
            for record in records:
                handle.write(json.dumps(record) + "\n")

    print(f"\n{ok} downloaded, {skipped} already held or queued, {failed} failed")
    if failed:
        print(f"failures appended to {FAILED.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
