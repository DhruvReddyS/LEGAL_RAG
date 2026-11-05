"""Every dated event in a case's files, in the order it happened.

An officer or advocate drops in an FIR, statements, notices and orders, and the first
thing they need is what happened when. This reads the dates the documents themselves
state, with no model, so nothing is inferred or reworded: each entry is the document's
own sentence, and it opens at the file and page it came from. A date in a document is
not proof that the event took place on it, and the screen says so.

Numeric dates are read day first, as Indian documents write them. Anything that is not
a real calendar date is dropped rather than guessed at.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Iterable

_MONTHS = {
    name: number
    for number, names in enumerate(
        (
            ("january", "jan"), ("february", "feb"), ("march", "mar"), ("april", "apr"),
            ("may",), ("june", "jun"), ("july", "jul"), ("august", "aug"),
            ("september", "sep", "sept"), ("october", "oct"), ("november", "nov"), ("december", "dec"),
        ),
        start=1,
    )
    for name in names
}
_MONTH = "|".join(sorted(_MONTHS, key=len, reverse=True))
_DAY_MONTH_YEAR = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:day\s+of\s+|of\s+)?({_MONTH})\.?,?\s+(\d{{4}})\b", re.IGNORECASE
)
_MONTH_DAY_YEAR = re.compile(rf"\b({_MONTH})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.IGNORECASE)
_MONTH_YEAR = re.compile(rf"\b(?:in|during|since|from|of|by|until)\s+({_MONTH})\.?,?\s+(\d{{4}})\b", re.IGNORECASE)
_NUMERIC = re.compile(r"(?<![\d/.-])(\d{1,2})([./-])(\d{1,2})\2(\d{4}|\d{2})(?![\d/-])")

EARLIEST_YEAR = 1900
SNIPPET_CHARACTERS = 280
MAX_EVENTS = 1000
_SENTENCE_END = re.compile(r"(?<=[.;!?])\s+(?=[A-Z0-9(\"'])|\n{2,}")


@dataclass(frozen=True)
class ChronologyEvent:
    date: str
    precision: str
    text: str
    document_id: str
    title: str
    page_start: int
    page_end: int


def _real_date(year: int, month: int, day: int, *, latest_year: int) -> date | None:
    if not EARLIEST_YEAR <= year <= latest_year:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def dates_in(text: str, *, latest_year: int) -> list[tuple[int, date, str]]:
    """(position, date, precision) for each date written in the text."""
    found: list[tuple[int, date, str]] = []
    taken: list[range] = []

    def add(match: re.Match[str], value: date | None, precision: str) -> None:
        if value is not None and not any(match.start() in span for span in taken):
            found.append((match.start(), value, precision))
            taken.append(range(match.start(), match.end()))

    for match in _DAY_MONTH_YEAR.finditer(text):
        add(match, _real_date(int(match[3]), _MONTHS[match[2].lower()], int(match[1]), latest_year=latest_year), "day")
    for match in _MONTH_DAY_YEAR.finditer(text):
        add(match, _real_date(int(match[3]), _MONTHS[match[1].lower()], int(match[2]), latest_year=latest_year), "day")
    for match in _NUMERIC.finditer(text):
        year = int(match[4])
        if len(match[4]) == 2:
            # 19/03/24 is 2024; 19/03/98 is 1998.
            year += 2000 if year <= latest_year % 100 else 1900
        add(match, _real_date(year, int(match[3]), int(match[1]), latest_year=latest_year), "day")
    for match in _MONTH_YEAR.finditer(text):
        add(match, _real_date(int(match[2]), _MONTHS[match[1].lower()], 1, latest_year=latest_year), "month")
    return sorted(found, key=lambda item: item[0])


def _sentence_around(text: str, position: int) -> str:
    start = 0
    end = len(text)
    for boundary in _SENTENCE_END.finditer(text):
        if boundary.end() <= position:
            start = boundary.end()
        elif boundary.start() >= position:
            end = boundary.start()
            break
    sentence = " ".join(text[start:end].split())
    if len(sentence) <= SNIPPET_CHARACTERS:
        return sentence
    # Keep the date in view when a sentence has to be cut.
    offset = max(0, min(position - start - SNIPPET_CHARACTERS // 2, len(sentence) - SNIPPET_CHARACTERS))
    cut = sentence[offset : offset + SNIPPET_CHARACTERS].strip()
    return f"{'…' if offset else ''}{cut}{'…' if offset + SNIPPET_CHARACTERS < len(sentence) else ''}"


def build_chronology(chunks: Iterable[dict[str, Any]], *, today: date | None = None) -> dict[str, Any]:
    """Ordered events from a case's indexed passages, one per date and sentence."""
    latest_year = (today or date.today()).year + 10
    seen: set[tuple[str, str]] = set()
    events: list[ChronologyEvent] = []
    documents: set[str] = set()
    for chunk in chunks:
        document_id = str(chunk.get("document_id") or "")
        documents.add(document_id)
        text = str(chunk.get("text") or "")
        for position, when, precision in dates_in(text, latest_year=latest_year):
            sentence = _sentence_around(text, position)
            # Overlapping passages repeat a sentence, and copies repeat it across files.
            identity = (when.isoformat(), re.sub(r"\W+", " ", sentence).casefold().strip())
            if identity in seen:
                continue
            seen.add(identity)
            page_start = int(chunk.get("page_start") or 1)
            events.append(
                ChronologyEvent(
                    date=when.isoformat(),
                    precision=precision,
                    text=sentence,
                    document_id=document_id,
                    title=str(chunk.get("title") or "Untitled document"),
                    page_start=page_start,
                    page_end=int(chunk.get("page_end") or page_start),
                )
            )
    events.sort(key=lambda event: (event.date, event.title, event.page_start, event.text))
    return {
        "events": [asdict(event) for event in events[:MAX_EVENTS]],
        "total_events": len(events),
        "documents_read": len(documents),
    }
