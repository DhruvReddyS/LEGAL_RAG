"""Every asserted passage has to be in the Act.

The registries quote the Sanhita so an officer can check them. A quote nobody compared
with the text is the same hazard as a hardcoded section number, so this compares them.

The extracted text prints margin notes in the middle of a sentence ("shall Person
forthwith communicate"). Matching therefore walks the quote's words in order, allowing
a few intruding words between any two, rather than requiring a contiguous string. A
quote from the wrong section, or one a paraphrase produced, does not survive that.

The corpus lives in the main checkout. Point LEGAL_KB_DIR at it if it is elsewhere; if
it cannot be found these tests skip and say so, and RUN_INTEGRATION=1 makes that a
failure.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from app.services.police_legal_sources import SOURCES
from app.services.police_offences import OFFENCES

DOCUMENTS = {
    "BNS": "gold-canonical-c9da896e7a16c481a4623578",
    "BNSS": "gold-canonical-5e60e2afe30d0fe7eca4f812",
    "BSA": "gold-canonical-13e2b6eb66add222c7262cca",
    "NDPS": "gold-canonical-95b15b3c31a31a766255d055",
    "POCSO": "gold-canonical-29627f9717f1e47f6d79ab78",
}

_TOKEN = re.compile(r"[a-z0-9]+")
_MAX_INTRUDING_WORDS = 12


def _corpus_dir() -> Path | None:
    configured = os.environ.get("LEGAL_KB_DIR")
    candidates = [Path(configured)] if configured else []
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidates.append(parent / "data" / "legal_kb")
    for candidate in candidates:
        if (candidate / "processed" / "extracted_text" / f"{DOCUMENTS['BNSS']}.json").exists():
            return candidate
    return None


CORPUS = _corpus_dir()


def _tokens(statute: str) -> list[str]:
    assert CORPUS is not None
    path = CORPUS / "processed" / "extracted_text" / f"{DOCUMENTS[statute]}.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    pages = document["pages"] if "pages" in document else [document]
    text = "\n".join(page.get("text", "") if isinstance(page, dict) else str(page) for page in pages)
    return _TOKEN.findall(text.lower())


_CACHE: dict[str, tuple[list[str], dict[str, list[int]]]] = {}


def _index(statute: str) -> tuple[list[str], dict[str, list[int]]]:
    if statute not in _CACHE:
        words = _tokens(statute)
        positions: dict[str, list[int]] = {}
        for at, word in enumerate(words):
            positions.setdefault(word, []).append(at)
        _CACHE[statute] = (words, positions)
    return _CACHE[statute]


def appears_in(statute: str, quote: str) -> bool:
    words, positions = _index(statute)
    wanted = _TOKEN.findall(quote.lower())
    assert wanted, quote
    for start in positions.get(wanted[0], []):
        at = start
        for word in wanted[1:]:
            window = words[at + 1 : at + 2 + _MAX_INTRUDING_WORDS]
            if word not in window:
                break
            at = at + 1 + window.index(word)
        else:
            return True
    return False


@pytest.fixture(autouse=True)
def _corpus_or_skip():
    if CORPUS is None:
        # Hosted CI has no corpus text: it is not in the public repository.
        if os.environ.get("RUN_INTEGRATION") == "1" and os.environ.get("GITHUB_ACTIONS") != "true":
            pytest.fail("The corpus text is required here and could not be found. Set LEGAL_KB_DIR.")
        pytest.skip("The corpus text is not available. Set LEGAL_KB_DIR to check the quotes.")


@pytest.mark.parametrize(("statute", "provision", "quote"), SOURCES, ids=[f"{s[0]} {s[1]}" for s in SOURCES])
def test_each_duty_passage_is_in_the_act(statute: str, provision: str, quote: str) -> None:
    assert appears_in(statute, quote), f"{statute} {provision}: not found in the corpus text: {quote!r}"


_ELEMENTS = [(offence.key, element) for offence in OFFENCES.values() for element in offence.elements]


@pytest.mark.parametrize(("offence", "element"), _ELEMENTS, ids=[f"{o}:{e.key}" for o, e in _ELEMENTS])
def test_each_offence_element_quotes_the_sanhita(offence: str, element) -> None:
    assert element.provision.startswith("BNS s."), element.key
    assert appears_in("BNS", element.source_quote), (
        f"{offence}/{element.key}: not found in the BNS text: {element.source_quote!r}"
    )


def test_the_matcher_rejects_what_the_act_does_not_say() -> None:
    """Otherwise everything above passes vacuously."""
    assert not appears_in("BNSS", "no woman shall be arrested at any time of day whatsoever")
    assert not appears_in("BNS", "whoever commits murder shall be punished with a warning")


def test_section_69_is_not_in_the_s193_2_list() -> None:
    """POL-5, against the text rather than against a constant in this repository."""
    assert appears_in("BNSS", "sections 64, 65, 66, 67, 68, 70, 71 of the Bharatiya Nyaya Sanhita")
    assert not appears_in("BNSS", "sections 64, 65, 66, 67, 68, 69, 70, 71 of the Bharatiya Nyaya Sanhita, 2023 or under sections 4")
