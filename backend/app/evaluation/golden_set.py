"""The golden set: questions with known-correct sources.

Every claim made about retrieval quality so far has been reasoned from a
handful of hand-run queries. This is the thing that turns those into numbers.

The central design constraint is that **items must survive re-chunking**.
Chunk IDs are content-addressed, so changing what gets embedded changes every
ID in the corpus. An item pinned to a chunk ID would be dead the moment the
index it exists to evaluate is rebuilt — which is exactly when it is needed.
So relevance is expressed against things that are stable: an Act and a section
number, or a phrase the correct passage must contain.

Expected abstentions are first-class. A corpus gap is not a retrieval failure,
and a system that answers a question it has no source for is worse than one
that declines. Scoring only answerable questions would reward exactly the wrong
behaviour.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

Expectation = Literal["answer", "abstain"]


@dataclass(frozen=True)
class RelevantSource:
    """One acceptable source for an answer, described so it outlives re-chunking.

    `act` and `section` identify a provision. `contains` matches a distinctive
    phrase in the passage. `title_contains` matches the document. Any field left
    unset is not checked, so a source can be pinned loosely (this Act) or
    tightly (this section of this Act, containing this phrase).
    """

    act: str | None = None
    section: str | None = None
    contains: str | None = None
    title_contains: str | None = None

    def matches(self, payload: dict[str, Any]) -> bool:
        if self.act is not None:
            haystack = " ".join(
                str(payload.get(field_name) or "")
                for field_name in ("act_name", "title", "source_type")
            ).casefold()
            if self.act.casefold() not in haystack:
                return False
        if self.section is not None:
            if str(payload.get("section") or "").casefold().strip() != self.section.casefold():
                return False
        if self.contains is not None:
            if self.contains.casefold() not in str(payload.get("text") or "").casefold():
                return False
        if self.title_contains is not None:
            if self.title_contains.casefold() not in str(payload.get("title") or "").casefold():
                return False
        return True


@dataclass(frozen=True)
class GoldenItem:
    id: str
    question: str
    expectation: Expectation
    relevant: tuple[RelevantSource, ...] = ()
    topic: str = "general"
    note: str = ""

    def is_relevant(self, payload: dict[str, Any]) -> bool:
        return any(source.matches(payload) for source in self.relevant)


@dataclass
class ItemResult:
    item: GoldenItem
    ranks: list[int] = field(default_factory=list)
    retrieved: int = 0

    @property
    def first_rank(self) -> int | None:
        return min(self.ranks) if self.ranks else None

    def recall_at(self, k: int) -> float:
        """Whether any correct source appears in the top k.

        Binary rather than proportional: a legal question usually has one
        governing provision, and several acceptable ways to reach it. Finding
        one of them is the outcome that matters.
        """
        return 1.0 if any(rank <= k for rank in self.ranks) else 0.0

    def reciprocal_rank(self) -> float:
        return 1.0 / self.first_rank if self.first_rank else 0.0

    def ndcg_at(self, k: int) -> float:
        """Binary-gain nDCG, bounded at 1.0.

        The ideal ranking is however many correct passages were found, placed
        at the top. An earlier version used the count of relevance *specs* as
        the denominator, but one spec can match many chunks — several passages
        of the same Act, say — so gain routinely exceeded the ideal and the
        metric reported values above 1.0, which nDCG cannot take.
        """
        import math

        within_k = [rank for rank in self.ranks if rank <= k]
        if not within_k:
            return 0.0
        gain = sum(1.0 / math.log2(rank + 1) for rank in within_k)
        ideal = sum(1.0 / math.log2(index + 2) for index in range(len(within_k)))
        return gain / ideal if ideal else 0.0

    @property
    def relevant(self) -> tuple[RelevantSource, ...]:
        return self.item.relevant


def load_golden_set(path: Path) -> list[GoldenItem]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    items: list[GoldenItem] = []
    for entry in raw["items"]:
        items.append(
            GoldenItem(
                id=entry["id"],
                question=entry["question"],
                expectation=entry["expectation"],
                relevant=tuple(
                    RelevantSource(**source) for source in entry.get("relevant", [])
                ),
                topic=entry.get("topic", "general"),
                note=entry.get("note", ""),
            )
        )
    _validate(items)
    return items


def _validate(items: list[GoldenItem]) -> None:
    seen: set[str] = set()
    for item in items:
        if item.id in seen:
            raise ValueError(f"duplicate golden item id: {item.id}")
        seen.add(item.id)
        if item.expectation == "answer" and not item.relevant:
            raise ValueError(
                f"{item.id}: an answerable item must name at least one source"
            )
        if item.expectation == "abstain" and item.relevant:
            raise ValueError(
                f"{item.id}: an abstention item must name no sources, "
                "or it is not testing abstention"
            )


def score(item: GoldenItem, payloads: list[dict[str, Any]]) -> ItemResult:
    """Rank positions, 1-indexed, of every retrieved passage that is correct."""
    result = ItemResult(item=item, retrieved=len(payloads))
    for position, payload in enumerate(payloads, start=1):
        if item.is_relevant(payload):
            result.ranks.append(position)
    return result
