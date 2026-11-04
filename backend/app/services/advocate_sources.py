"""How a retrieved passage is described, and how evidence is gathered for a tool.

Every advocate surface renders the same source shape, so a currency label can't
appear in one tool and go missing in another. Labels come from
`citation_labels_for`, the one call every other lane uses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.ingestion.init_qdrant import ADVOCATE_CASE_DATA, GLOBAL_LEGAL_CORPUS
from app.services.citation_status import citation_labels_for
from app.services.retrieval import (
    HybridRetrievalService,
    RetrievalFilters,
    RetrievalHit,
    RetrievalTarget,
)

PASSAGE_CHARACTERS = 1400
PROMPT_PASSAGE_CHARACTERS = 2000


def source_from_payload(
    payload: dict[str, Any],
    *,
    score: float | None = None,
    verified: bool = False,
) -> dict[str, Any]:
    labels = citation_labels_for(payload)
    private = payload.get("corpus_scope") == "private_case"
    return {
        "point_id": str(payload.get("chunk_id") or ""),
        "chunk_id": str(payload.get("chunk_id") or ""),
        "title": str(payload.get("case_title") or payload.get("title") or "Untitled"),
        "source_type": str(payload.get("source_type") or payload.get("doc_type") or "case_document"),
        "section": str(payload.get("section") or "") or None,
        "page_start": int(payload.get("page_start") or 1),
        "page_end": int(payload.get("page_end") or payload.get("page_start") or 1),
        "excerpt": str(payload.get("text") or "")[:PASSAGE_CHARACTERS],
        "relevance_score": score,
        "verification_status": "verified" if verified else "unverified",
        "scope": "private_case" if private else "global",
        "source_url": payload.get("source_url") or None,
        "document_id": payload.get("canonical_document_id") or payload.get("document_id"),
        "court": payload.get("court") or None,
        "decision_year": payload.get("decision_year") or None,
        **labels,
    }


@dataclass
class Evidence:
    """Passages a model may cite, by id, and the sources they render as."""

    passages: dict[str, str] = field(default_factory=dict)
    payloads: dict[str, dict[str, Any]] = field(default_factory=dict)
    scores: dict[str, float | None] = field(default_factory=dict)
    # Held back: an instrument superseded with no savings governs nothing and
    # may not ground a published claim. Counted so the holding-back is visible.
    withheld_superseded: int = 0

    def add(self, payload: dict[str, Any], *, score: float | None = None) -> None:
        chunk_id = str(payload.get("chunk_id") or "")
        text = str(payload.get("text") or "")
        if not chunk_id or not text.strip():
            return
        if citation_labels_for(payload).get("current_status") == "superseded":
            self.withheld_superseded += 1
            return
        self.passages[chunk_id] = text
        self.payloads[chunk_id] = payload
        self.scores[chunk_id] = score

    def source(self, chunk_id: str, *, verified: bool) -> dict[str, Any]:
        return source_from_payload(self.payloads[chunk_id], score=self.scores.get(chunk_id), verified=verified)

    def sources(self, *, verified: bool = False) -> list[dict[str, Any]]:
        return [self.source(chunk_id, verified=verified) for chunk_id in self.payloads]

    def prompt_block(self) -> str:
        blocks = []
        for chunk_id, payload in self.payloads.items():
            status = citation_labels_for(payload).get("current_status")
            blocks.append(
                f"ID: {chunk_id}\n"
                f"TITLE: {payload.get('case_title') or payload.get('title') or 'Untitled'}\n"
                f"STATUS: {status}\n"
                f"TEXT: {self.passages[chunk_id][:PROMPT_PASSAGE_CHARACTERS]}"
            )
        return "\n\n---\n\n".join(blocks) or "(no passages)"

    def __bool__(self) -> bool:
        return bool(self.passages)


def evidence_from_hits(hits: list[RetrievalHit]) -> Evidence:
    evidence = Evidence()
    for hit in hits:
        evidence.add(dict(hit.payload), score=float(hit.reranker_score))
    return evidence


async def gather_evidence(
    retrieval: HybridRetrievalService,
    query: str,
    *,
    case_id: str | None,
    include_corpus: bool = True,
    candidate_limit: int = 30,
    result_limit: int = 10,
) -> Evidence:
    """Law from the corpus, and only this case's own files. Never another case's."""
    targets: list[RetrievalTarget] = []
    if include_corpus:
        targets.append(
            RetrievalTarget(
                GLOBAL_LEGAL_CORPUS,
                RetrievalFilters(current_only=False, corpus_tiers=["gold", "extended"]),
            )
        )
    if case_id:
        targets.append(
            RetrievalTarget(ADVOCATE_CASE_DATA, RetrievalFilters(corpus_tiers=[], case_ids=[case_id]))
        )
    hits, _ = await retrieval.search_across_collections_with_timings(
        query[:4000], targets=targets, candidate_limit=candidate_limit, result_limit=result_limit
    )
    return evidence_from_hits(hits)
