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
_ATTEMPTS = 2
# Telugu takes three to four times the tokens of the same English, so a whole
# answer ran past the output limit and lost its ending (and its sources). Pieces
# this size fit with room to spare, and a failed check retries one piece, not all.
_PIECE_CHARACTERS = 600
_CACHE_SIZE = 256
_MARKER = re.compile(r"\[Source\s+\d+\]", re.IGNORECASE)
_NUMBER = re.compile(r"\d+")
# The model translated the word "Source" itself (into Telugu for "holiday"), so the
# markers go in as [S1] and come back as [Source 1].
_SHORT_MARKER = re.compile(r"\[\s*S\s*(\d+)\s*\]")
_NATIVE_DIGITS = str.maketrans("०१२३४५६७८९౦౧౨౩౪౫౬౭౮౯", "01234567890123456789")

_cache: OrderedDict[tuple[str, str], str] = OrderedDict()


class TranslationRejected(Exception):
    """The model's text could not be shown as a translation of this answer."""


def _prompt(answer: str, language: str) -> str:
    return f"""Translate this legal information from English into simple, natural {language} for an ordinary reader.

Rules:
- Translate every sentence. Add nothing, leave nothing out, and do not explain or advise.
- Keep every marker such as [S1] exactly as written, in the same place. Do not translate it.
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


def _shield(text: str) -> str:
    return _MARKER.sub(lambda m: f"[S{_NUMBER.search(m.group(0)).group(0)}]", text)


def _unshield(text: str) -> str:
    return _SHORT_MARKER.sub(lambda m: f"[Source {m.group(1)}]", text)


def _clean(text: str) -> str:
    """Qwen3 sometimes finishes, writes "/no_think" and "</think>", and translates
    the piece a second time. The first copy is the answer; the rest would double
    every number and fail the check."""
    text = text.split("</think>", 1)[0]
    return re.sub(r"\s*/no_think\s*$", "", text).strip()


def _pieces(answer: str) -> list[str]:
    """Paragraphs, packed into pieces of about _PIECE_CHARACTERS. A longer paragraph
    is split at its line breaks; a single longer line stays whole."""
    blocks: list[str] = []
    for paragraph in re.split(r"\n\s*\n", answer.strip()):
        if len(paragraph) <= _PIECE_CHARACTERS:
            blocks.append(paragraph)
            continue
        current = ""
        for line in paragraph.split("\n"):
            if current and len(current) + len(line) + 1 > _PIECE_CHARACTERS:
                blocks.append(current)
                current = line
            else:
                current = f"{current}\n{line}" if current else line
        blocks.append(current)
    # A heading travels with what follows it. A piece ending on a bare heading is
    # what set off the repeated translation described in _clean.
    joined: list[str] = []
    for block in blocks:
        if joined and re.fullmatch(r"#+ [^\n]*", joined[-1].strip()):
            joined[-1] = f"{joined[-1]}\n\n{block}"
        else:
            joined.append(block)
    blocks = joined
    pieces: list[str] = []
    for block in blocks:
        if pieces and len(pieces[-1]) + len(block) + 2 <= _PIECE_CHARACTERS:
            pieces[-1] = f"{pieces[-1]}\n\n{block}"
        else:
            pieces.append(block)
    return pieces


def _piece_kept(original: str, translated: str) -> bool:
    normalised = translated.translate(_NATIVE_DIGITS)
    markers = lambda text: Counter(re.sub(r"\s+", " ", m).casefold() for m in _MARKER.findall(text))  # noqa: E731
    return markers(original) == markers(normalised) and Counter(_NUMBER.findall(original)) == Counter(
        _NUMBER.findall(normalised)
    )


async def _translate_piece(llm: Any, piece: str, language: str) -> str:
    # A dropped marker is often a one-off, so a piece gets a second try before the
    # reader is told no translation is available.
    for _ in range(_ATTEMPTS):
        text, _metrics = await llm.generate_with_metrics(_prompt(_shield(piece), language), num_predict=_PREDICT_LIMIT)
        translated = _unshield(_clean(text))
        if _piece_kept(piece, translated):
            return translated
    raise TranslationRejected(language)


async def translate_answer(llm: Any, *, message_id: str, answer: str, language_code: str) -> str:
    key = (message_id, language_code)
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    language, _ = LANGUAGES[language_code]
    parts = [await _translate_piece(llm, piece, language) for piece in _pieces(answer)]
    translated = "\n\n".join(parts)
    # The whole is checked again: the pieces each kept their own, and this also
    # requires the reader's script to appear at all.
    if not is_faithful(answer, translated, language_code):
        raise TranslationRejected(language_code)
    _cache[key] = translated
    while len(_cache) > _CACHE_SIZE:
        _cache.popitem(last=False)
    return translated
