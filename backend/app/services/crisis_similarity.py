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
optimistic. Hindi and Telugu, in both scripts, caught 10 of 13 held-out messages
with no false alarm on 15 ordinary questions, before the last four examples were
added for the kinds it missed.

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
    # People in crisis write in their own language, and often in Latin script.
    # Awaiting review by a native speaker with crisis training. A wrong example
    # costs a notice beside an answer, so these ship rather than wait.
    "मैं अपनी जान देना चाहता हूँ",
    "मैं आत्महत्या करना चाहती हूँ",
    "अब जीने का मन नहीं है",
    "मेरा पति मुझे मार रहा है",
    "कोई मुझे जान से मारने की धमकी दे रहा है",
    "मेरे साथ बलात्कार हुआ है",
    "मेरा बच्चा लापता हो गया है",
    "मेरे खाते से धोखे से पैसे निकल गए",
    "main apni jaan dena chahta hoon",
    "mujhe ab jeena nahi hai",
    "mera pati mujhe maar raha hai",
    "mere saath balatkar hua hai",
    "నేను ఆత్మహత్య చేసుకోవాలనుకుంటున్నాను",
    "నాకు బతకాలని లేదు",
    "నా భర్త నన్ను కొడుతున్నాడు",
    "నన్ను చంపేస్తానని బెదిరిస్తున్నారు",
    "నాపై అత్యాచారం జరిగింది",
    "నా బిడ్డ కనిపించడం లేదు",
    "నా ఖాతా నుండి మోసంతో డబ్బు తీసేశారు",
    "naaku bathakalani ledu",
    "naa bhartha nannu kodutunnadu",
    "main khudkushi kar lunga",
    "wo mujhe maar dalega",
    "maine bahut saari goliyan kha li hain",
    "మాత్రలు మింగి చనిపోతాను",
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
        self._examples: asyncio.Task[list[Sequence[float]]] | None = None

    async def _embed_examples(self) -> list[Sequence[float]]:
        embedded = await self._encoder.embed_documents(list(CRISIS_EXAMPLES))
        return [item.dense for item in embedded]  # type: ignore[attr-defined]

    def prepare(self) -> None:
        """Start embedding the examples now, so the first person does not wait."""
        if self._examples is None or (self._examples.done() and self._examples.exception()):
            self._examples = asyncio.create_task(self._embed_examples())

    async def _example_vectors(self) -> list[Sequence[float]]:
        # Shielded because callers run under a timeout. Cancelling this work when
        # it took longer than the timeout meant it restarted on every request and
        # never finished, so on a slow machine every question showed the helplines.
        self.prepare()
        return await asyncio.shield(self._examples)

    async def sounds_like_crisis(self, query: str) -> bool:
        examples = await self._example_vectors()
        vector = await self._encoder.embed_query(query)
        return max(_cosine(vector, example) for example in examples) >= self._threshold
