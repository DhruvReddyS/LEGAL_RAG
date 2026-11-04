"""Does this question sound like someone in crisis, whatever words it uses?

citizen_safety matches explicit phrasing and replaces the answer, so it has to
be narrow. Measured on phrasing it was not written against, it fired on 4 of 20
real crisis messages: "I took a lot of pills" and "there is a man outside my
door with a knife" reached retrieval with nothing to mark them. A pattern list
cannot close that gap, because people do not describe a crisis in a fixed form.

This compares the question's meaning to worded examples, using the query encoder
retrieval already holds, so it needs no model call and no second model. At 0.65
it caught 28 of 28 held-out crisis messages and also flagged 10 of 86 ordinary
legal questions. The threshold was chosen on that same set, so 28 of 28 is
optimistic.

That false-alarm rate is why this never replaces an answer. It only shows
helplines beside one: a false alarm costs a small notice, and a miss costs far
more. Lowering the threshold is the safe direction to move in. Raising it needs
a measurement.
"""

from __future__ import annotations

import asyncio
from typing import Protocol, Sequence

CRISIS_SIMILARITY_THRESHOLD = 0.65

CRISIS_EXAMPLES: tuple[str, ...] = (
    "I want to end my life",
    "I am planning to kill myself tonight",
    "I cannot cope and I want to die",
    "I have swallowed tablets to die",
    "I see no reason to stay alive",
    "everyone would be better off without me",
    "I am standing on the roof and going to jump",
    "I have been harming myself",
    "I am thinking about suicide",
    "my husband is beating me",
    "a man is attacking me right now",
    "someone broke into my home and I am hiding",
    "he has a weapon and is threatening me",
    "I am locked in a room and being hurt",
    "I was raped and I need help",
    "I am being followed and I am scared",
    "people are coming to hurt me",
    "I am being held by force",
    "a child near me is being abused",
    "my child has gone missing",
    "a young girl is being forced to marry tomorrow",
    "a child is being beaten by an adult",
    "I lost money to an online scam just now",
    "money was taken from my bank account by fraud",
    "I shared my OTP and my account was emptied",
    "a caller pretending to be an officer made me pay money",
)


class _QueryEncoder(Protocol):
    async def embed_query(self, query: str) -> Sequence[float]: ...

    async def embed_documents(self, texts: list[str], *, batch_size: int = 8) -> list[object]: ...


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norms = sum(a * a for a in left) ** 0.5 * sum(b * b for b in right) ** 0.5
    return dot / norms if norms else 0.0


class CrisisSimilarity:
    def __init__(self, encoder: _QueryEncoder, *, threshold: float = CRISIS_SIMILARITY_THRESHOLD) -> None:
        self._encoder = encoder
        self._threshold = threshold
        self._examples: list[Sequence[float]] | None = None
        self._examples_lock = asyncio.Lock()

    async def _example_vectors(self) -> list[Sequence[float]]:
        async with self._examples_lock:
            if self._examples is None:
                embedded = await self._encoder.embed_documents(list(CRISIS_EXAMPLES))
                self._examples = [item.dense for item in embedded]  # type: ignore[attr-defined]
        return self._examples

    async def sounds_like_crisis(self, query: str) -> bool:
        examples = await self._example_vectors()
        vector = await self._encoder.embed_query(query)
        return max(_cosine(vector, example) for example in examples) >= self._threshold
