"""Bridge the words a citizen uses to the words the statute book uses.

Retrieval is semantic, but not magic. Asked "I bought a defective phone online
and the seller refuses a refund, what are my rights", it returned the
Bharatiya Nyaya Sanhita and nothing from consumer law -- while the corpus held
247 passages of the Consumer Protection Act, 2019 and the e-commerce rules
made under it. Rephrased as "what are my rights as a consumer when goods are
defective", the same corpus returned the Act four times out of four.

The gap is vocabulary. A citizen writes "phone", "seller", "refund"; the Act
says "goods", "defect", "deficiency in service", "complainant". A citizen
module that only works once the citizen already knows the legal term is not a
citizen module.

So the retrieval query is widened, never replaced: the person's own words stay
and the statutory vocabulary is added after them, which costs nothing when the
person already used legal language and recovers the whole domain when they did
not. Nothing here decides an answer. Verification still requires every
published claim to name a chunk that was actually retrieved, so a wrong
widening can cost recall but cannot produce an unsupported statement.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Bridge:
    """Lay cues that imply a legal domain, and the terms that find it."""

    domain: str
    cues: tuple[re.Pattern[str], ...]
    terms: str


def _any(*words: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(w, re.I) for w in words)


BRIDGES: tuple[Bridge, ...] = (
    Bridge(
        "consumer",
        _any(r"\brefund", r"\breplace(?:ment)?\b.{0,24}\b(?:product|item|phone|device)",
             r"\bdefect(?:ive)?\b", r"\bfaulty\b", r"\bwarrant(?:y|ies)\b",
             r"\b(?:seller|shopkeeper|retailer|e-?commerce|online (?:order|purchase|seller|shopping))\b",
             r"\bnot (?:delivered|working)\b", r"\boverchar(?:ge|ged)\b", r"\bmisleading ad"),
        "consumer rights defect in goods deficiency in service complaint before the "
        "consumer commission unfair trade practice Consumer Protection Act",
    ),
    Bridge(
        "tenancy",
        _any(r"\blandlord\b", r"\btenant\b", r"\brent\b", r"\bsecurity deposit\b",
             r"\bevict(?:ion|ed)?\b", r"\blease\b", r"\bvacate\b", r"\bpaying guest\b"),
        "landlord and tenant lease rent security deposit eviction possession "
        "transfer of property rent control",
    ),
    Bridge(
        "cyber_harassment",
        _any(r"\bharass(?:ing|ment|ed)?\b.{0,30}\b(?:online|internet|social media|whatsapp|instagram)",
             r"\b(?:online|cyber)\b.{0,16}\b(?:harass|stalk|abuse|bully|threat)",
             r"\bmorphed\b", r"\bobscene\b.{0,20}\b(?:message|photo|picture|video)",
             r"\btrolling\b", r"\bfake (?:profile|account)\b", r"\bblackmail", r"\bsextortion\b"),
        "stalking cyber stalking obscene material in electronic form publishing or "
        "transmitting obscene material criminal intimidation Information Technology Act "
        "intermediary grievance officer",
    ),
    Bridge(
        "wages",
        # Both orders occur and the first draft only matched one: "wages have
        # not been paid" fired, "has not paid my wages" did not.
        _any(r"\b(?:salary|wages|pay)\b.{0,24}\bnot (?:paid|been paid)\b",
             r"\bnot (?:been )?paid\b.{0,24}\b(?:salary|wages|dues)\b",
             r"\bunpaid\b.{0,12}\b(?:salary|wages)\b", r"\bemployer\b.{0,24}\brefus",
             r"\bgratuity\b", r"\bprovident fund\b", r"\bterminated\b.{0,24}\bwithout\b"),
        "wages employer employee payment of wages deduction industrial dispute "
        "labour authority Code on Wages",
    ),
    Bridge(
        "land",
        _any(r"\bencroach(?:ed|ment|ing)?\b", r"\bboundary\b.{0,20}\b(?:dispute|wall)",
             r"\btrespass", r"\bneighbou?r\b.{0,30}\b(?:land|plot|wall|property)",
             r"\bpossession\b.{0,20}\b(?:land|plot)", r"\bmutation\b"),
        "encroachment possession trespass injunction title to immovable property "
        "land revenue survey settlement recovery of possession",
    ),
    Bridge(
        "family",
        _any(r"\bdivorce\b", r"\bmaintenance\b", r"\balimony\b", r"\bcustody\b",
             r"\bdowry\b", r"\bdomestic violence\b", r"\bin-?laws?\b.{0,24}\b(?:harass|beat|torture)"),
        "marriage divorce judicial separation maintenance custody of children "
        "domestic violence protection order",
    ),
    Bridge(
        "police_process",
        _any(r"\bFIR\b", r"\barrest(?:ed)?\b", r"\bpolice\b.{0,24}\brefus",
             r"\bbail\b", r"\bcustody\b", r"\bcomplaint\b.{0,20}\bpolice\b",
             r"\bremand\b", r"\bsummons\b"),
        "first information report cognizable offence arrest grounds of arrest bail "
        "magistrate police station Bharatiya Nagarik Suraksha Sanhita",
    ),
    Bridge(
        "accident",
        _any(r"\b(?:road|motor|vehicle|car|bike|truck)\b.{0,16}\baccident\b",
             r"\bhit (?:and run|by a)\b", r"\binsurance claim\b", r"\bcompensation\b.{0,24}\baccident\b"),
        "motor accident claims tribunal compensation third party insurance "
        "negligence Motor Vehicles Act",
    ),
    Bridge(
        "rti",
        _any(r"\b(?:copy|certified copy)\b.{0,30}\b(?:record|document|file)\b",
             r"\binformation\b.{0,24}\b(?:government|public authority|department)\b",
             r"\bRTI\b", r"\bpublic record\b"),
        "right to information public authority public information officer "
        "first appeal certified copy of a public document",
    ),
    Bridge(
        "legal_aid",
        _any(r"\bfree legal\b", r"\blegal aid\b", r"\bcannot afford\b.{0,24}\b(?:lawyer|advocate)",
             r"\blok adalat\b", r"\bfree lawyer\b"),
        "free legal aid entitlement legal services authority eligibility for legal "
        "services lok adalat panel advocate",
    ),
)

# Widening a query that already uses legal language only dilutes it.
_ALREADY_LEGAL = re.compile(
    r"\b(?:section|article|act,|sanhita|adhiniyam|under the|rule \d|regulation)\b", re.I)


def widen_for_retrieval(query: str) -> tuple[str, tuple[str, ...]]:
    """Return the retrieval query with statutory vocabulary added, and the domains hit.

    The person's own wording is preserved in full and always comes first.
    """
    matched = [b for b in BRIDGES if any(cue.search(query) for cue in b.cues)]
    if not matched:
        return query, ()
    # More than two domains means the cues are firing on something generic;
    # adding every vocabulary set would bury the question itself.
    if len(matched) > 2:
        matched = matched[:2]
    added = " ".join(b.terms for b in matched)
    return f"{query} {added}", tuple(b.domain for b in matched)
