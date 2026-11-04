"""Stand-ins for the corpus and the model that behave like them.

The Qdrant fake evaluates the real filter objects against payloads shaped as
ingestion writes them, so a filter on the wrong key finds nothing here too. The
model fake reads the prompt it is sent, as the real one must. It can cite only
ids the prompt offers and can quote only what the prompt shows, so a prompt that
drops the passages produces nothing rather than a passing test.
"""

from __future__ import annotations

import re
from types import SimpleNamespace
from typing import Any

from qdrant_client import models

from app.agents.advocate_agents import BriefDraft, ComparisonDraft, DebateDraft, GroundsDraft
from app.agents.verification_agent import VerificationBatch
from app.schemas.strategy import DefenceAnalysisDraft
from app.services.retrieval import RetrievalHit


def judgment_chunk(
    document_id: str,
    title: str,
    number: int,
    text: str,
    *,
    court: str = "Supreme Court of India",
    year: int | None = 2023,
    cited_cases: tuple[str, ...] = (),
    cited_provisions: tuple[str, ...] = (),
    page: int | None = None,
    tier: str = "gold",
) -> SimpleNamespace:
    page_number = page if page is not None else number
    return SimpleNamespace(
        id=f"{document_id}-point-{number}",
        payload={
            "chunk_id": f"{document_id}-chunk-{number}",
            "canonical_document_id": document_id,
            "document_id": f"doc-{document_id}",
            "source_type": "judgment",
            "corpus_tier": tier,
            "title": title,
            "case_title": title,
            "court": court,
            "decision_year": year or 0,
            **({"decision_date": f"{year}-03-01T00:00:00Z"} if year else {}),
            "source_url": f"https://example.gov.in/{document_id}.pdf",
            "page_start": page_number,
            "page_end": page_number,
            "text": text,
            "cited_cases": list(cited_cases),
            "cited_provisions": list(cited_provisions),
        },
    )


def _matches(condition: Any, payload: dict[str, Any]) -> bool:
    value = payload.get(condition.key)
    match = condition.match
    if isinstance(match, models.MatchValue):
        return value == match.value or (isinstance(value, list) and match.value in value)
    if isinstance(match, models.MatchAny):
        return value in match.any or (isinstance(value, list) and bool(set(value) & set(match.any)))
    raise AssertionError(f"unexpected condition {condition}")


class FakeQdrant:
    def __init__(self, records: list[SimpleNamespace]) -> None:
        self.records = records
        self.scrolls = 0
        self.fail = False

    async def scroll(self, *, collection_name, scroll_filter, limit, offset, with_payload, with_vectors):
        if self.fail:
            raise OSError("qdrant is down")
        self.scrolls += 1
        kept = [
            record for record in self.records
            if all(_matches(condition, record.payload) for condition in (scroll_filter.must or []))
        ]
        start = int(offset or 0)
        page = kept[start : start + limit]
        following = start + limit if start + limit < len(kept) else None
        if isinstance(with_payload, list):
            page = [
                SimpleNamespace(id=item.id, payload={key: item.payload.get(key) for key in with_payload})
                for item in page
            ]
        return page, following

    async def retrieve(self, *, collection_name, ids, with_payload, with_vectors):
        if self.fail:
            raise OSError("qdrant is down")
        wanted = set(ids)
        return [record for record in self.records if record.id in wanted]


def hit(record: SimpleNamespace, score: float = 0.9) -> RetrievalHit:
    return RetrievalHit(
        point_id=record.id, payload=dict(record.payload), dense_score=score, sparse_score=score,
        fused_score=score, reranker_score=score,
    )


class FakeRetrieval:
    """Ranks by shared words, honours filters, and keeps case data inside its case."""

    def __init__(self, corpus: list[SimpleNamespace], case_files: list[SimpleNamespace] | None = None) -> None:
        self.corpus = corpus
        self.case_files = case_files or []
        self.client = FakeQdrant([*corpus, *self.case_files])
        self.calls: list[dict[str, Any]] = []
        self.fail = False

    @staticmethod
    def _score(query: str, text: str) -> int:
        words = set(re.findall(r"[a-z]{4,}", query.casefold()))
        return len(words & set(re.findall(r"[a-z]{4,}", text.casefold())))

    def _rank(self, records: list[SimpleNamespace], query: str, limit: int) -> list[RetrievalHit]:
        scored = sorted(records, key=lambda item: -self._score(query, str(item.payload.get("text"))))
        return [hit(item) for item in scored[:limit]]

    async def search(self, query, *, filters=None, candidate_limit=20, result_limit=5, rerank=True, with_lane_scores=False):
        if self.fail:
            raise OSError("retrieval is down")
        self.calls.append({"query": query, "filters": filters})
        kept = self.corpus
        if filters is not None:
            if filters.source_types:
                kept = [item for item in kept if item.payload.get("source_type") in filters.source_types]
            if filters.courts:
                kept = [item for item in kept if item.payload.get("court") in filters.courts]
            if filters.year_from is not None:
                kept = [item for item in kept if (item.payload.get("decision_year") or 0) >= filters.year_from]
            if filters.year_to is not None:
                kept = [item for item in kept if 0 < (item.payload.get("decision_year") or 0) <= filters.year_to]
        return self._rank(kept, query, result_limit)

    async def search_across_collections_with_timings(self, query, *, targets, candidate_limit=20, result_limit=5, **_):
        if self.fail:
            raise OSError("retrieval is down")
        self.calls.append({"query": query, "targets": targets})
        kept: list[SimpleNamespace] = []
        for target in targets:
            if target.filters.case_ids:
                kept.extend(
                    item for item in self.case_files
                    if item.payload.get("case_id") in target.filters.case_ids
                )
            else:
                kept.extend(self.corpus)
        return self._rank(kept, query, result_limit), SimpleNamespace()


_PASSAGE = re.compile(
    r"^(?:CHUNK_)?ID: (?P<id>[^\n]+)\nTITLE: [^\n]*\n(?:STATUS: [^\n]*\n)?TEXT: (?P<text>.*?)(?=\n\n---\n\n|\n\nFIRST|\n\nSECOND|\Z)",
    re.M | re.S,
)
_CLAIM = re.compile(
    r"CLAIM (?P<index>\d+): (?P<claim>.*?)\n(?:SOURCE TEXT|LAW):\n(?P<source>.*?)(?=\nUNVERIFIED FACTS:|\nUSER'S UNVERIFIED ACCOUNT:|\n\nCLAIM \d+:|\Z)",
    re.S,
)
_WORD = re.compile(r"[a-z]{4,}")


def first_sentence(text: str) -> str:
    return " ".join(re.split(r"(?<=[.;])\s", text.strip())[0].split())


class PromptReadingLLM:
    """Proposes from the passages it was shown, and judges by reading them.

    Alongside what is supported it proposes the things the discipline has to stop:
    a claim citing a passage that was never offered, one with a section number
    that is not in its source, and an outcome prediction.
    """

    def __init__(self, *, verifier_available: bool = True, drafter_available: bool = True) -> None:
        self.verifier_available = verifier_available
        self.drafter_available = drafter_available
        self.prompts: list[str] = []
        self.verifier_prompts: list[str] = []
        self.draft_calls = 0
        self.short_verdicts = False
        self.fail_after_draft_calls: int | None = None

    @staticmethod
    def _passages(prompt: str) -> list[tuple[str, str]]:
        return [(match["id"].strip(), match["text"].strip()) for match in _PASSAGE.finditer(prompt)]

    def _traps(self, passage_id: str, source_key: str = "source_ids") -> list[dict[str, Any]]:
        return [
            {"text": "It is settled by a passage nobody retrieved that bail follows.", source_key: ["never-offered-id"]},
            {"text": "The passage rests the matter on section 999 of the Sanhita.", source_key: [passage_id]},
            {"text": "The accused will win this application outright.", source_key: [passage_id]},
        ]

    async def structured(self, prompt: str, schema: type) -> Any:
        self.prompts.append(prompt)
        if isinstance(schema, type) and issubclass(schema, VerificationBatch):
            return self._verify(prompt, schema)
        self.draft_calls += 1
        if self.fail_after_draft_calls is not None and self.draft_calls > self.fail_after_draft_calls:
            raise RuntimeError("the model went away")
        if not self.drafter_available:
            raise RuntimeError("the model is down")
        passages = self._passages(prompt)
        if schema is DefenceAnalysisDraft:
            law = [(pid, text) for pid, text in passages if pid != "case-scenario-input"]
            return DefenceAnalysisDraft.model_validate(
                {
                    "summary": "Model text that must not reach the reader.",
                    "points": [
                        {"category": "defence_point", "point": first_sentence(text), "source_chunk_ids": [pid]}
                        for pid, text in law[:2]
                    ]
                    + [{"category": "defence_point", "point": "The accused will win this application outright.", "source_chunk_ids": [law[0][0]]}],
                }
            )
        if schema is GroundsDraft:
            return GroundsDraft.model_validate({"grounds": self._points(passages)})
        if schema is DebateDraft:
            return DebateDraft.model_validate({"arguments": self._points(passages)[:3]})
        if schema is BriefDraft:
            return BriefDraft.model_validate(
                {
                    "claims": [
                        {"text": first_sentence(text), "source_ids": [passage_id], "section": "chronology" if index % 2 else "issues"}
                        for index, (passage_id, text) in enumerate(passages)
                    ]
                    + [{"text": "The accused will win this application outright.", "source_ids": [passages[0][0]], "section": "issues"}]
                }
            )
        if schema is ComparisonDraft:
            head, _, tail = prompt.partition("\n\nSECOND: ")
            first = self._passages(head)
            second = self._passages(tail)
            return ComparisonDraft.model_validate(
                {
                    "points": [
                        {
                            "dimension": "The incident",
                            "first": first_sentence(first[0][1]),
                            "first_source_ids": [first[0][0]],
                            "second": first_sentence(second[0][1]),
                            "second_source_ids": [second[0][0]],
                        },
                        {
                            # Each side cites the other judgment's passage.
                            "dimension": "Crossed citations",
                            "first": first_sentence(second[0][1]),
                            "first_source_ids": [second[0][0]],
                            "second": first_sentence(first[0][1]),
                            "second_source_ids": [first[0][0]],
                        },
                    ]
                }
            )
        raise AssertionError(f"unexpected schema {schema}")

    def _points(self, passages: list[tuple[str, str]]) -> list[dict[str, Any]]:
        law = [(pid, text) for pid, text in passages if pid != "matter-facts-input"]
        if not law:
            return []
        points = [{"text": first_sentence(text), "source_ids": [pid]} for pid, text in law[:2]]
        return points + self._traps(law[0][0])

    def _verify(self, prompt: str, schema: type) -> Any:
        self.verifier_prompts.append(prompt)
        if not self.verifier_available:
            raise RuntimeError("the verifier is down")
        verdicts = []
        for match in _CLAIM.finditer(prompt):
            claim_words = set(_WORD.findall(match["claim"].casefold()))
            source_words = set(_WORD.findall(match["source"].casefold()))
            verdicts.append("yes" if claim_words <= source_words else "no")
        if self.short_verdicts:
            verdicts = verdicts[:-1]
        return schema(verdicts=verdicts)
