from __future__ import annotations

import re
from dataclasses import dataclass


# Acronyms are legal retrieval keys used by Acts represented in the governed
# corpus. Matching is algorithmic; no query/topic-specific branch exists.
KNOWN_LEGAL_ACRONYMS = frozenset(
    {
        "bns",
        "bnss",
        "bsa",
        "crpc",
        "ipc",
        "it",
        "ndps",
        "pocso",
    }
)

LEGAL_ACRONYM_EXPANSIONS: dict[str, tuple[str, ...]] = {
    "bns": ("bharatiya", "nyaya", "sanhita"),
    "bnss": ("bharatiya", "nagarik", "suraksha", "sanhita"),
    "bsa": ("bharatiya", "sakshya", "adhiniyam"),
    "crpc": ("criminal", "procedure", "code"),
    "ipc": ("indian", "penal", "code"),
    "ndps": ("narcotic", "drugs", "psychotropic", "substances"),
    "pocso": ("protection", "children", "sexual", "offences"),
}


@dataclass(frozen=True)
class LegalTermNormalization:
    original: str
    normalized: str
    corrections: tuple[tuple[str, str], ...]


def _damerau_levenshtein_at_most_one(left: str, right: str) -> bool:
    """Return whether equal-length terms differ by one edit/transposition."""
    if left == right:
        return True
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        mismatches = [index for index, pair in enumerate(zip(left, right)) if pair[0] != pair[1]]
        if len(mismatches) == 1:
            return True
        if len(mismatches) == 2:
            first, second = mismatches
            return (
                second == first + 1
                and left[first] == right[second]
                and left[second] == right[first]
            )
        return False
    shorter, longer = (left, right) if len(left) < len(right) else (right, left)
    short_index = long_index = edits = 0
    while short_index < len(shorter) and long_index < len(longer):
        if shorter[short_index] == longer[long_index]:
            short_index += 1
            long_index += 1
            continue
        edits += 1
        long_index += 1
        if edits > 1:
            return False
    return True


def normalize_legal_terms(query: str) -> LegalTermNormalization:
    """Correct a unique one-edit match to a known legal acronym.

    Ambiguous matches and ordinary words are left unchanged. Requiring at
    least four letters prevents common short words from being rewritten.
    """
    corrections: list[tuple[str, str]] = []

    def replace(match: re.Match[str]) -> str:
        token = match.group(0)
        folded = token.casefold()
        if folded in KNOWN_LEGAL_ACRONYMS or len(folded) < 3:
            return token
        # A three-character floor lets bns, bsa and ipc be corrected. The
        # unique-match requirement below still refuses anything ambiguous, so
        # "bnss" cannot be pulled toward "bns" and vice versa.
        candidates = sorted(
            acronym
            for acronym in KNOWN_LEGAL_ACRONYMS
            if len(acronym) >= 3 and _damerau_levenshtein_at_most_one(folded, acronym)
        )
        if len(candidates) != 1:
            return token
        corrected = candidates[0]
        corrections.append((token, corrected.upper()))
        return corrected.upper()

    normalized = re.sub(r"\b[A-Za-z][A-Za-z0-9]*\b", replace, query)
    return LegalTermNormalization(
        original=query,
        normalized=normalized,
        corrections=tuple(corrections),
    )
