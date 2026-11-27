"""Which community's marriage law a marriage question is about.

India has a separate marriage and divorce law for each community: the Hindu
Marriage Act for Hindus, Sikhs, Jains and Buddhists, the Divorce Act, 1869 and
the Indian Christian Marriage Act for Christians, the Parsi Marriage and Divorce
Act, Muslim personal law with the Dissolution of Muslim Marriages Act, and the
Special Marriage Act for civil and interfaith marriages. Their divorce sections
are worded almost identically -- cruelty, desertion, adultery -- so retrieval
cannot tell them apart and picks by surface wording. On ILSIC's layperson
questions labelled with the Hindu Marriage Act (28 of 100), the reader was shown
the HMA for 5 and another community's law for 13; "We are Parsis and want a
divorce by mutual consent" was shown HMA s.13B.

So a marriage question is shown only the marriage law of the community it names:
- a marriage under the Special Marriage Act (court, civil or interfaith marriage)
  is governed by that Act whatever the spouses' religion, so it wins outright;
- otherwise every community the question names is kept;
- a question that names none is, for the large majority of people who ask it, a
  Hindu Marriage Act question, and that is how lawyers answering those questions
  read it.
Laws that are not marriage laws (maintenance under the BNSS, domestic violence,
dowry) are never touched.
"""

from __future__ import annotations

import re

HINDU, CHRISTIAN, PARSI, MUSLIM, SPECIAL, FOREIGN = (
    "hindu", "christian", "parsi", "muslim", "special", "foreign",
)

# What a question says that puts it under a community's law. Plurals and
# adjectives count: "we are Parsis", "Christians", "Islamic".
_CUES: dict[str, re.Pattern[str]] = {
    HINDU: re.compile(r"\b(?:hindus?|sikhs?|jains?|buddhists?|hindu marriage)\b", re.I),
    CHRISTIAN: re.compile(r"\b(?:christians?|church|catholics?|protestants?|divorce act)\b", re.I),
    PARSI: re.compile(r"\b(?:parsis?|parsees?|zoroastrians?)\b", re.I),
    MUSLIM: re.compile(r"\b(?:muslims?|islam\w*|nikah|nikaah|talaq|talak|khula|mehr|meher)\b", re.I),
    SPECIAL: re.compile(
        r"\b(?:special marriage|court marriage|civil marriage|registered under the special|"
        r"inter[\s-]?(?:faith|religio\w*)|different religions?|other religion)\b",
        re.I,
    ),
    FOREIGN: re.compile(r"\b(?:foreign marriage|married abroad)\b", re.I),
}

# The Acts that belong to each community, by name.
_ACTS: dict[str, re.Pattern[str]] = {
    HINDU: re.compile(r"hindu marriage act", re.I),
    CHRISTIAN: re.compile(r"\bthe divorce act\b|divorce act,? 1869|christian marriage", re.I),
    PARSI: re.compile(r"parsi marriage", re.I),
    MUSLIM: re.compile(r"dissolution of muslim marriages|muslim women|muslim personal law", re.I),
    SPECIAL: re.compile(r"special marriage act", re.I),
    FOREIGN: re.compile(r"foreign marriage act", re.I),
}

_MARRIAGE_TOPIC = re.compile(
    r"\b(?:marri\w*|divorc\w*|wife|wives|husbands?|spouses?|matrimon\w*|conjugal|"
    r"judicial separation|alimony|in[\s-]?laws?|nikah|talaq)\b",
    re.I,
)


def named_communities(query: str) -> frozenset[str]:
    text = str(query or "")
    return frozenset(name for name, cue in _CUES.items() if cue.search(text))


def is_marriage_question(query: str) -> bool:
    return bool(_MARRIAGE_TOPIC.search(str(query or "")))


def governing_communities(query: str) -> frozenset[str]:
    """The communities whose marriage law may be shown for this question."""
    named = named_communities(query)
    if SPECIAL in named:
        return frozenset({SPECIAL})
    return named or frozenset({HINDU})


def marriage_law_community(payload: dict) -> str | None:
    name = f"{payload.get('act_name') or ''} | {payload.get('title') or ''}"
    return next((community for community, act in _ACTS.items() if act.search(name)), None)


def unasked_personal_law(query: str, hits: list) -> frozenset[str]:
    """Chunk ids of marriage laws that govern a community the question is not about."""
    if not is_marriage_question(query):
        return frozenset()
    allowed = governing_communities(query)
    unasked: set[str] = set()
    for hit in hits:
        community = marriage_law_community(hit.payload)
        if community is not None and community not in allowed:
            unasked.add(str(hit.payload.get("chunk_id")))
    return frozenset(unasked)
