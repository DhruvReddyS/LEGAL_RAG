"""Which Acts the corpus holds, and which sections of each.

Listing them means reading every bare-act point, so it happens once in the
background and the answer is kept. A request never scrolls: it gets the index,
or is told the index is still being built. Past the TTL the old index goes on
serving while a new one is built, since an Act list a little out of date is
better than a page that makes someone wait.

Only what `law_lookup` can open is listed, so a section shown here never leads
to a dead end for a reason this file could have known.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from qdrant_client import models

from app.core.config import settings
from app.services.law_lookup import _ACT_TEXT, _SHORT_NAMES, _code_from_shorthand, _names_the_act, parse_citation
from app.services.quarantine import is_quarantined

logger = logging.getLogger(__name__)

INDEX_TTL_SECONDS = 6 * 60 * 60
# After a failed build, requests may ask again only after this long.
RETRY_AFTER_SECONDS = 60
SCROLL_PAGE = 2048
MAX_SEARCH_RESULTS = 50
MAX_CITATION_CHARS = 160

_WORD = re.compile(r"[a-z0-9]+")
_SECTION = re.compile(r"^(\d{1,4})([A-Z]{0,3})$")
_CONSTITUTION_WORDS = ("constitution", "of", "india")


@dataclass(frozen=True)
class ActEntry:
    id: str
    name: str
    words: tuple[str, ...]
    sections: tuple[str, ...]


@dataclass(frozen=True)
class ActIndex:
    acts: tuple[ActEntry, ...]
    by_id: dict[str, ActEntry]
    built_at: float


def _words(name: object) -> tuple[str, ...]:
    words = tuple(_WORD.findall(str(name).casefold()))
    return words[1:] if words[:1] == ("the",) and len(words) > 1 else words


def clean_section(raw: object) -> str | None:
    """"35(3)" is section 35. Anything that is not a section number is left out."""
    base = str(raw or "").split("(", 1)[0].strip().upper()
    return base if _SECTION.match(base) else None


def section_sort_key(section: str) -> tuple[int, str]:
    """Numeric, so 2 comes before 10 and 120A directly after 120."""
    match = _SECTION.match(section)
    return (int(match.group(1)), match.group(2)) if match else (10**6, section)


def _is_constitution(words: tuple[str, ...]) -> bool:
    return words[:3] == _CONSTITUTION_WORDS


def citation_for(act_name: str, section: str) -> str | None:
    """Text the lookup reads back as this section of this Act, or None if it would not."""
    noun = "Article" if _is_constitution(_words(act_name)) else "Section"
    lead = f"{noun} {section} of "
    name = act_name.strip()
    if len(lead) + len(name) > MAX_CITATION_CHARS:
        # Every word asked for must be in the title, so a shorter name still finds it.
        name = name[: MAX_CITATION_CHARS - len(lead)].rsplit(" ", 1)[0].rstrip(" ,")
    citation = f"{lead}{name}"
    parsed = parse_citation(citation)
    if parsed is None or parsed.section != section or not _names_the_act(act_name, parsed.act):
        return None
    return citation


def build_index(pairs: list[tuple[str, str]], *, built_at: float = 0.0) -> ActIndex:
    """From (act_name, section) pairs, however often each repeats."""
    grouped: dict[tuple[str, ...], tuple[Counter[str], set[str]]] = {}
    for raw_name, raw_section in pairs:
        name = str(raw_name or "").strip()
        section = clean_section(raw_section)
        words = _words(name)
        if not name or not words or section is None:
            continue
        names, sections = grouped.setdefault(words, (Counter(), set()))
        names[name] += 1
        sections.add(section)
    acts = []
    for words, (names, sections) in grouped.items():
        acts.append(
            ActEntry(
                id=hashlib.sha256(" ".join(words).encode()).hexdigest()[:16],
                # The commonest spelling, with ties settled so a rebuild gives the same one.
                name=sorted(names.items(), key=lambda item: (-item[1], item[0]))[0][0],
                words=words,
                sections=tuple(sorted(sections, key=section_sort_key)),
            )
        )
    acts.sort(key=lambda act: act.words)
    return ActIndex(acts=tuple(acts), by_id={act.id: act for act in acts}, built_at=built_at)


def _query_words(name: str) -> list[str]:
    """Shorthand people type for an Act, then the words themselves."""
    code = _code_from_shorthand(name)
    expanded = _ACT_TEXT.get(code) if code else _SHORT_NAMES.get(name.strip().casefold())
    return [word for word in _WORD.findall((expanded or name).casefold()) if word not in {"the", "of", "and"}]


def search_acts(index: ActIndex, name: str, *, limit: int = MAX_SEARCH_RESULTS) -> tuple[list[ActEntry], int]:
    """Each word typed begins some word of the title. In Python, as in the lookup,
    because the store's text match is case-sensitive."""
    wanted = _query_words(name)
    if not wanted:
        return list(index.acts[:limit]), len(index.acts)
    found = [act for act in index.acts if all(any(word.startswith(term) for word in act.words) for term in wanted)]
    # A title that opens with what was typed is more likely the one meant.
    found.sort(key=lambda act: (not act.words[0].startswith(wanted[0]), len(act.words), act.words))
    return found[:limit], len(found)


async def _scroll_pairs(client: Any, collection: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    offset = None
    while True:
        batch, offset = await client.scroll(
            collection_name=collection,
            # The Constitution is stored as a bare act too, so one exact filter covers both.
            scroll_filter=models.Filter(
                must=[models.FieldCondition(key="document_type", match=models.MatchValue(value="bare_act"))]
            ),
            limit=SCROLL_PAGE,
            offset=offset,
            with_payload=["act_name", "section", "canonical_document_id", "document_id"],
            with_vectors=False,
        )
        for point in batch:
            payload = point.payload or {}
            document = payload.get("canonical_document_id") or payload.get("document_id") or point.id
            if not is_quarantined(document):
                pairs.append((str(payload.get("act_name") or ""), str(payload.get("section") or "")))
        if offset is None:
            return pairs


class ActBrowser:
    def __init__(self, *, ttl: float = INDEX_TTL_SECONDS, clock: Callable[[], float] = time.monotonic) -> None:
        self._ttl = ttl
        self._clock = clock
        self._index: ActIndex | None = None
        self._task: asyncio.Task[None] | None = None
        self._failed_at: float | None = None

    @property
    def failing(self) -> bool:
        """The last build failed and there is nothing to serve in its place."""
        return self._index is None and self._failed_at is not None and self._task is None

    def current(self, client: Any, *, collection: str | None = None) -> ActIndex | None:
        """The index if there is one, starting a build if it is missing or old. Never waits."""
        now = self._clock()
        stale = self._index is None or now - self._index.built_at >= self._ttl
        recently_failed = self._failed_at is not None and now - self._failed_at < RETRY_AFTER_SECONDS
        if stale and self._task is None and not recently_failed:
            self._task = asyncio.create_task(self._build(client, collection or settings.qdrant_global_collection))
        return self._index

    async def _build(self, client: Any, collection: str) -> None:
        try:
            pairs = await _scroll_pairs(client, collection)
            self._index = await asyncio.to_thread(build_index, pairs, built_at=self._clock())
            self._failed_at = None
            logger.info("Act index built: %d acts from %d points", len(self._index.acts), len(pairs))
        except Exception as exc:  # noqa: BLE001 - runs detached; the next request may try again
            self._failed_at = self._clock()
            logger.warning("Act index build failed: %s", type(exc).__name__)
        finally:
            self._task = None

    async def wait_for_build(self) -> None:
        """For tests."""
        if self._task is not None:
            await self._task


act_browser = ActBrowser()
