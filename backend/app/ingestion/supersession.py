"""Which Acts in the corpus have been replaced, and by what.

21.1% of the corpus is the Indian Penal Code, the Code of Criminal Procedure
and the Indian Evidence Act, all repealed on 1 July 2024. Their replacements
account for 4%. Repealed law outnumbers current law five to one, so a citizen
question about criminal law is answered from provisions that no longer apply
unless something says otherwise.

This is a table, not a heuristic. Repeal is a fact with a date and a successor,
and inferring it from a title would get the Code of Criminal Procedure, 1898
wrong -- it was replaced by the 1973 Code, not by the 2023 Sanhita.

What this does *not* do is mark these Acts `is_superseded`. That flag means
"cannot ground a published claim", and these Acts still govern: an offence
committed before 1 July 2024 is tried under the old codes (BNSS s.531 saves
pending proceedings). Answering such a question from the IPC is correct. What
was wrong was doing it silently.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Replacement:
    replaced_by: str
    repealed_on: str  # ISO date the repeal took effect.


# Matched against the start of act_name or title, so a circular *about* section
# 498A of the Penal Code is not itself labelled repealed -- only the Act is.
_REPLACED: tuple[tuple[re.Pattern[str], Replacement], ...] = (
    (
        re.compile(r"^(?:the\s+)?code\s+of\s+criminal\s+procedure,?\s*1898\b", re.I),
        Replacement("The Code of Criminal Procedure, 1973", "1974-04-01"),
    ),
    (
        re.compile(r"^(?:the\s+)?code\s+of\s+criminal\s+procedure\b", re.I),
        Replacement("The Bharatiya Nagarik Suraksha Sanhita, 2023", "2024-07-01"),
    ),
    (
        re.compile(r"^(?:the\s+)?indian\s+penal\s+code\b", re.I),
        Replacement("The Bharatiya Nyaya Sanhita, 2023", "2024-07-01"),
    ),
    (
        re.compile(r"^(?:the\s+)?indian\s+evidence\s+act\b", re.I),
        Replacement("The Bharatiya Sakshya Adhiniyam, 2023", "2024-07-01"),
    ),
)


def replacement_for(*names: str | None) -> Replacement | None:
    """The Act that replaced this document, if it is one of the repealed codes.

    Names are tried in order, so a curated `act_name` wins over a scraped
    `title`. The 1898 Code is listed before the general Code of Criminal
    Procedure rule because both match it and the first wins.
    """
    for name in names:
        cleaned = (name or "").strip()
        if not cleaned:
            continue
        for pattern, replacement in _REPLACED:
            if pattern.match(cleaned):
                return replacement
    return None
