"""Put a verified answer into the reader's language, or say that it could not be done.

Verification judges English claims against English sources, so translation comes after
it and never replaces it: the English answer stays on screen as the verified one, and
this is labelled a machine translation. A translation may not change what was verified,
so it is checked before it is shown. Every number and source marker must survive, which
catches a changed period or section and a dropped claim. A failed check shows nothing,
because no translation is safer than a wrong deadline in a language the reader trusts.
"""

from __future__ import annotations

import re
from collections import Counter, OrderedDict
from typing import Any

LANGUAGES = {"hi": ("Hindi", re.compile(r"[ऀ-ॿ]")), "te": ("Telugu", re.compile(r"[ఀ-౿]"))}

MAX_CHARACTERS = 8000
_PREDICT_LIMIT = 2400
_CACHE_SIZE = 256
_MARKER = re.compile(r"\[Source\s+\d+\]", re.IGNORECASE)
_NUMBER = re.compile(r"\d+")
_NATIVE_DIGITS = str.maketrans("०१२३४५६७८९౦౧౨౩౪౫౬౭౮౯", "01234567890123456789")

_cache: OrderedDict[tuple[str, str], str] = OrderedDict()


class TranslationRejected(Exception):
    """The model's text could not be shown as a translation of this answer."""


def _prompt(answer: str, language: str) -> str:
    return f"""Translate this legal information from English into simple, natural {language} for an ordinary reader.

Rules:
- Translate every sentence. Add nothing, leave nothing out, and do not explain or advise.
- Keep every marker such as [Source 1] exactly as written, in the same place.
- Keep all numbers, dates, durations and section numbers exactly as written, in the same digits.
- Keep the names of Acts in English. Keep the markdown headings and list markers.
- Reply with the translation only.

TEXT:
{answer}"""


def is_faithful(answer: str, translated: str, language_code: str) -> bool:
    """Whether everything checkable in the answer came through unchanged."""
    _, script = LANGUAGES[language_code]
    if not script.search(translated):
        return False
    normalised = translated.translate(_NATIVE_DIGITS)
    markers = lambda text: Counter(re.sub(r"\s+", " ", m).casefold() for m in _MARKER.findall(text))  # noqa: E731
    if markers(answer) != markers(normalised):
        return False
    return Counter(_NUMBER.findall(answer)) == Counter(_NUMBER.findall(normalised))


async def translate_answer(llm: Any, *, message_id: str, answer: str, language_code: str) -> str:
    key = (message_id, language_code)
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    language, _ = LANGUAGES[language_code]
    text, _ = await llm.generate_with_metrics(_prompt(answer, language), num_predict=_PREDICT_LIMIT)
    translated = text.strip()
    if not is_faithful(answer, translated, language_code):
        raise TranslationRejected(language_code)
    _cache[key] = translated
    while len(_cache) > _CACHE_SIZE:
        _cache.popitem(last=False)
    return translated
