"""Reach the provision in force by following what the corpus already cites.

A citizen asks "how is an FIR registered?". BNSS s.173 answers it and
contains none of those words -- it says "information relating to the
commission of a cognizable offence". Measured: the section does not appear
in the top 100 for that question, while its own text retrieves it at rank 1.
So the index is sound and the gap is between how statutes are drafted and
how people ask.

What *does* rank for that question is judgments about FIR registration, and
those judgments cite CrPC s.154 -- the repealed provision, because they
predate the 2023 Sanhitas. The official NCRB concordance says CrPC s.154 is
now BNSS s.173.

So the corpus can reach the governing provision on its own: read what the
retrieved passages rely on, follow those citations forward through the
concordance, and fetch the result. It is how a lawyer works -- read the
commentary, follow it to the statute -- and it needs no model, no
hand-written statutory phrasing, and no re-indexing.

Measured over five questions whose governing provision retrieval could not
reach at all:

    how is an FIR registered          -> BNSS s.173, cited 9 times
    anticipatory bail grounds         -> BNSS s.482, cited 6 times
    arrest without a warrant          -> BNSS s.35,  cited 4 times
    which law governs theft           -> BNS s.303, reached
    what is default bail              -> not reached (see below)

Default bail is the honest miss: the passages cite CrPC ss.437 and 437A,
which map to the BNSS bail sections rather than to s.187, whose proviso is
what actually creates the entitlement. Following citations reaches what the
sources rely on, which is not always what the question needs.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from app.services.section_mapping import map_sections

__all__ = ["FollowedProvision", "provisions_worth_following"]

# How the citation extractor keys the repealed codes, and the concordance's
# name for each. Only the three replaced codes are followed: a citation to a
# code still in force needs no forwarding.
_REPEALED_CODE_KEYS = {"crpc": "CrPC", "ipc": "IPC", "evidence": "IEA"}

# Bounded deliberately. A judgment cites many provisions in passing, and
# fetching every successor would swamp the result set with material the
# question never asked about.
MAX_FOLLOWED = 3

# One citation is an aside. This asks for corroboration across the retrieved
# passages before treating a provision as the one they rest on.
MIN_CITATIONS = 2


@dataclass(frozen=True)
class FollowedProvision:
    code: str
    section: str
    citations: int
    via: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.code, self.section)


def provisions_worth_following(hits: list) -> list[FollowedProvision]:
    """The in-force provisions the retrieved passages rely on, most-cited first.

    Deterministic: the same hits give the same list, ordered by citation
    weight and then by provision, so a measurement means something.
    """
    weight: Counter[tuple[str, str]] = Counter()
    via: dict[tuple[str, str], str] = {}

    for hit in hits:
        payload = getattr(hit, "payload", None) or {}
        for reference in payload.get("cited_provisions") or []:
            key, _, section = str(reference).lower().partition(":")
            code = _REPEALED_CODE_KEYS.get(key)
            if code is None or not section:
                continue
            # One citation is one vote, however many rows the concordance
            # holds for it. CrPC s.154 has three -- BNSS 173, 173(1) and
            # 173(3) -- and counting rows made a single passing mention
            # outvote a provision three passages agreed on.
            successors = {
                (mapping.to_code, str(mapping.to_section).split("(")[0])
                for mapping in map_sections(code, section)
                if mapping.has_successor
            }
            for target in successors:
                weight[target] += 1
                via.setdefault(target, f"{code} s.{section}")

    ranked = sorted(
        (item for item in weight.items() if item[1] >= MIN_CITATIONS),
        key=lambda item: (-item[1], item[0][0], item[0][1]),
    )
    return [
        FollowedProvision(code=code, section=section, citations=count, via=via[(code, section)])
        for (code, section), count in ranked[:MAX_FOLLOWED]
    ]
