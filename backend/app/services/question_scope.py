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

import re

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
