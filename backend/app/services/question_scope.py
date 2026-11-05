"""Is this question about the law of another country?

Corpusil holds Indian law. Retrieval always returns its nearest neighbours, and
Indian statutes share words with any legal question, so "How do I get a divorce
in England?" was answered from the Special Marriage Act 1954. The words matched
and the country did not, and no relevance floor can see that.

Being connected to another country does not put a question out of scope. A
husband in Canada who abandons his wife in Hyderabad, an extradition to the United
States, or a visa overstayed in India are all questions of Indian law. So this
refuses only when a foreign place is where the asked-about rule would apply, and
nothing ties the question to India. A person merely being abroad does not count.

It fails towards answering: a question this misses still has to clear every
other gate, while a question it wrongly catches gets no answer at all.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any, Sequence

_PLACES = (
    r"afghanistan|america|argentina|australia|austria|bahrain|bangladesh|belgium|"
    r"bhutan|brazil|california|canada|china|denmark|dubai|egypt|england|europe|"
    r"finland|france|germany|greece|hong kong|indonesia|iran|iraq|ireland|israel|"
    r"italy|japan|kenya|kuwait|london|malaysia|maldives|melbourne|mexico|myanmar|"
    r"nepal|netherlands|new york|new zealand|nigeria|norway|oman|ontario|pakistan|"
    r"philippines|poland|portugal|qatar|russia|saudi arabia|scotland|singapore|"
    r"south africa|south korea|spain|sri lanka|sweden|switzerland|sydney|texas|"
    r"thailand|toronto|turkey|the uae|uae|the uk|uk|ukraine|united arab emirates|"
    r"united kingdom|the united states|united states|the usa|usa|the us|us|"
    r"vancouver|vietnam|wales"
)

# Written case-sensitively for "US" and "UK" below; "us" is also a pronoun.
_RULE_APPLIES_THERE = re.compile(rf"\b(?:in|within)\s+({_PLACES})\b", re.IGNORECASE)
_LAW_OF_THERE = re.compile(
    rf"\b(?:laws?|rules?|courts?|government|embassy|consulate)\s+(?:of|in)\s+({_PLACES})\b",
    re.IGNORECASE,
)
_ADJECTIVAL_LAW = re.compile(
    r"\b(?:american|australian|british|canadian|chinese|dutch|emirati|english|french|"
    r"german|japanese|pakistani|russian|singaporean|uae|uk|us)\s+"
    r"(?:law|laws|courts?|immigration|visa|citizenship|tax|taxes)\b",
    re.IGNORECASE,
)
_FOREIGN_INSTRUMENT = re.compile(r"\bgreen\s+card\b|\bH-?1B\b|\bschengen\b", re.IGNORECASE)

# Someone being abroad says where they are, not which law is asked about.
_PERSON_BEFORE_PLACE = re.compile(
    r"\b(?:husband|wife|spouse|son|daughter|child|children|father|mother|parents?|"
    r"brother|sister|relative|friend|accused|fianc[eé]e?|nri|agent|consultant)\s+"
    r"(?:who\s+(?:is|lives|works)\s+|living\s+|working\s+|settled\s+|staying\s+|based\s+|now\s+)?"
    r"(?:in|within)\s+$",
    re.IGNORECASE,
)

# Anything tying the question to India, or to a provision it names, keeps it in.
_TIED_TO_INDIA = re.compile(
    r"\b(?:india|indian|bharat|nri|oci|pio|extradit\w*|fema|passport act|"
    r"foreigners act|foreign marriage act|section|sections|article|articles|"
    r"bns|bnss|bsa|ipc|crpc|cpc|\w+\s+act)\b|"
    r"\b(?:andhra|telangana|hyderabad|delhi|mumbai|bengaluru|bangalore|chennai|"
    r"kolkata|pune|kerala|gujarat|punjab|supreme court|high court|magistrate|fir)\b",
    re.IGNORECASE,
)


def _names_place_as_a_pronoun(match: re.Match[str]) -> bool:
    """"in us" reads as a pronoun; only the capitalised country counts."""
    return match.group(1).casefold() in {"us", "uk"} and not match.group(1).isupper()


def asks_about_foreign_law(question: str) -> bool:
    """Whether the rule being asked about belongs to another country."""
    text = " ".join(question.split())
    if not text or _TIED_TO_INDIA.search(text):
        return False
    if _FOREIGN_INSTRUMENT.search(text) or _ADJECTIVAL_LAW.search(text):
        return True
    for pattern in (_LAW_OF_THERE, _RULE_APPLIES_THERE):
        for match in pattern.finditer(text):
            if _names_place_as_a_pronoun(match):
                continue
            if pattern is _RULE_APPLIES_THERE and _PERSON_BEFORE_PLACE.search(
                text[: match.start(1)]
            ):
                continue
            return True
    return False


# ---------------------------------------------------------------- off topic
#
# "Which shares should I buy this month?" passed the relevance floor, because SEBI
# circulars say "shares" and "buy". The words are in the corpus and the question is
# not about law, which matching words cannot see, so this compares meaning.

_NOT_LEGAL_EXAMPLES: tuple[str, ...] = (
    "How do I make chicken curry at home?",
    "What should I cook for dinner tonight?",
    "What medicine should I take for a headache?",
    "How much ibuprofen can an adult take?",
    "What are the symptoms of diabetes?",
    "What diet helps me lose weight quickly?",
    "Which mutual fund will give the best returns?",
    "Is gold a good investment right now?",
    "Which stock will go up next week?",
    "Who won the football match yesterday?",
    "Who is the best batsman in the world?",
    "When is the next Olympic games?",
    "How do I fix a bug in my JavaScript code?",
    "Write a program that reverses a string",
    "What is the tallest mountain in the world?",
    "How far is the moon from the earth?",
    "What is the weather forecast for tomorrow?",
    "What are the best places to visit on holiday?",
    "Which phone should I buy under twenty thousand rupees?",
    "Recommend a good movie to watch this weekend",
    "Solve this equation for x",
    "How do I grow tomatoes in my garden?",
    "How can I become more confident when speaking?",
    "Write me a poem about the rain",
)
_LEGAL_EXAMPLES: tuple[str, ...] = (
    "Can my landlord keep my deposit when I move out?",
    "My employer has not paid my salary for two months",
    "The seller refuses to refund a defective phone",
    "What can I do if someone cheats me of money?",
    "My neighbour has built a wall on my land",
    "Can my husband take the children away from me?",
    "Someone is harassing me online with fake photos",
    "How do I get a copy of my father's property papers?",
    "What happens if I do not pay a loan back?",
    "Can the police take my phone without asking?",
    "What can I do about a loud factory next to my house?",
    "How do I claim money after a road accident?",
    "My shop was sealed by the municipality without notice",
    "Do I have to pay tax on money from selling my house?",
    "A hospital refused to give me my medical records",
    "A company sold me shares by misleading me",
    "My son was expelled from school without any hearing",
    "What should I do when I receive a notice from a bank?",
)
# Any of these and the question stays in, whatever its meaning scores: refusing a
# real legal question costs far more than one more evidence check.
_LEGAL_WORD = re.compile(
    r"\b(?:law|laws|legal|illegal|lawful|unlawful|legally|act|section|article|rule|rules|"
    r"court|judge|magistrate|police|fir|arrest\w*|bail|custody|offen[cs]e\w*|crime\w*|"
    r"criminal|punish\w*|penalty|fine|sue|suing|complaint|petition|appeal|rights?|"
    r"contract|licen[cs]e|permit\w*|notice|summons|warrant|lawyer|advocate|tenant|landlord|"
    r"divorce|maintenance|custody|dowry|inherit\w*|will|property|consumer|compensation|"
    r"bns|bnss|bsa|ipc|crpc|cpc|rti|pocso|sebi|rbi|government|constitution\w*)\b",
    re.IGNORECASE,
)
# Measured: refused 12 of 14 unseen off-topic questions, and none of 16 lay legal
# questions or the 94 answerable golden questions, the highest of which scored 0.022.
_NOT_LEGAL_MARGIN = 0.05


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norms = sum(a * a for a in left) ** 0.5 * sum(b * b for b in right) ** 0.5
    return dot / norms if norms else 0.0


class OffTopicCheck:
    """Whether a question is closer to everyday non-legal asks than to legal ones.

    Uses the query encoder retrieval already holds, and the query's own vector is
    cached there, so the search itself pays for it. Any failure answers "not off
    topic": the other gates still apply, and this one must never cost an answer.
    """

    def __init__(self, encoder: Any, *, margin: float = _NOT_LEGAL_MARGIN) -> None:
        self._encoder = encoder
        self._margin = margin
        self._examples: asyncio.Task[tuple[list, list]] | None = None

    async def _embed_examples(self) -> tuple[list, list]:
        count = len(_NOT_LEGAL_EXAMPLES)
        embedded = await self._encoder.embed_documents([*_NOT_LEGAL_EXAMPLES, *_LEGAL_EXAMPLES])
        vectors = [item.dense for item in embedded]
        return vectors[:count], vectors[count:]

    async def scores(self, question: str) -> tuple[float, float]:
        if self._examples is None or (self._examples.done() and self._examples.exception()):
            self._examples = asyncio.create_task(self._embed_examples())
        not_legal, legal = await asyncio.shield(self._examples)
        vector = await self._encoder.embed_query(question)
        return (
            max(_cosine(vector, example) for example in not_legal),
            max(_cosine(vector, example) for example in legal),
        )

    async def is_off_topic(self, question: str) -> bool:
        if _LEGAL_WORD.search(question):
            return False
        try:
            not_legal, legal = await self.scores(question)
        except Exception:  # noqa: BLE001 - see the class docstring
            return False
        return not_legal - legal >= self._margin


def off_topic_check_for(service: Any) -> OffTopicCheck:
    """One per encoder, so the examples are embedded once whichever lane asks first."""
    check = getattr(service, "_off_topic_check", None)
    if not isinstance(check, OffTopicCheck):
        check = OffTopicCheck(service)
        service._off_topic_check = check
    return check
