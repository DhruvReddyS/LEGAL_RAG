"""The authorities a Deep run has found, offered before the answer exists.

Deep Review takes one to three minutes, and until today it showed a progress
label for all of it: the citation and answer-chunk events were written only
after verification finished, so measured time-to-first-useful-output was
identical to end-to-end -- 92 seconds at p50. A reader waiting that long with
nothing but "Checking every statement against its source" has no way to tell
a working system from a stuck one, and no way to start reading.

Retrieval finishes at about 7% of that wall time. What it has at that point is
real, source-backed and useful: the governing provisions and judgments the
question reaches, each with its act, section, pages, currency and repeal
status. Publishing those early is not publishing an answer. Nothing here is a
legal claim, nothing has been through the verifier, and the payload says so in
a field rather than in a tooltip -- `verification_status` is "unverified" and
`is_final_answer` is false on every entry, so a surface cannot render these as
the answer by accident.

Global corpus only. A case-scoped Deep run also retrieves the owner's own case
material, and interim progress is not the place to start widening where that
text appears.
"""

from __future__ import annotations

from typing import Any

from app.ingestion.init_qdrant import GLOBAL_LEGAL_CORPUS
from app.services.citation_status import citation_labels
from app.services.currency import resolve_currency


# Enough to recognise the provision and decide whether to wait, not enough to
# read as an answer. The final citation carries 900.
EXCERPT_CHARACTERS = 320

# One event per run, so the payload is bounded by what retrieval returns
# rather than by what a surface might ask for.
MAX_LOCATED_SOURCES = 8


def _compact(text: Any, limit: int = EXCERPT_CHARACTERS) -> str:
    rendered = " ".join(str(text or "").split())
    if len(rendered) <= limit:
        return rendered
    return rendered[: limit - 1].rstrip() + "\u2026"


def located_sources(hits: list[Any]) -> list[dict[str, Any]]:
    """Display-safe descriptions of the passages retrieval located."""
    sources: list[dict[str, Any]] = []
    for number, hit in enumerate(hits, 1):
        payload = dict(getattr(hit, "payload", None) or {})
        collection = str(payload.get("collection_name") or GLOBAL_LEGAL_CORPUS)
        if collection != GLOBAL_LEGAL_CORPUS:
            continue
        labels = citation_labels(payload)
        sources.append(
            {
                "number": number,
                "chunk_id": str(payload.get("chunk_id") or getattr(hit, "point_id", "")),
                "title": str(payload.get("title") or "Unknown source"),
                "source_type": str(payload.get("source_type") or "unknown"),
                "act_name": payload.get("act_name") or None,
                "section": payload.get("section") or None,
                "court": payload.get("court") or None,
                "page_start": int(payload.get("page_start") or 1),
                "page_end": int(
                    payload.get("page_end") or payload.get("page_start") or 1
                ),
                "source_url": payload.get("source_url") or None,
                "excerpt": _compact(payload.get("text")),
                "currency_status": resolve_currency(payload).status,
                "repeal_label": labels.get("repeal_label"),
                "replaced_by": labels.get("replaced_by"),
                "repealed_on": labels.get("repealed_on"),
                # Stated per entry, not per payload. A surface that renders a
                # list cannot drop a field it never reads, and these two are
                # the difference between "found" and "answered".
                "verification_status": "unverified",
                "is_final_answer": False,
            }
        )
        if len(sources) >= MAX_LOCATED_SOURCES:
            break
    return sources
