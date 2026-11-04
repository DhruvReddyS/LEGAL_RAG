"""Every provision the advocate tools state must be on the page it is pinned to.

The bail and limitation calculators quote statute without a model in the loop,
so nothing at runtime would catch a mistyped word or a wrong page. This reads
the corpus's own extracted text. Where the corpus is not on this machine the
comparison skips, and the shape checks still run.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from app.services.advocate_provisions import PROVISIONS


def _extracted_text_root() -> Path | None:
    configured = os.environ.get("LEGAL_KB_EXTRACTED_TEXT")
    if configured:
        return Path(configured)
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "data" / "legal_kb" / "processed" / "extracted_text"
        if candidate.is_dir():
            return candidate
    return None


def _normalise(value: str) -> str:
    value = re.sub(r"_{3,}", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _pages(root: Path, document_id: str) -> dict[int, str]:
    data = json.loads((root / f"{document_id}.json").read_text(encoding="utf-8"))
    return {int(page["page_number"]): _normalise(page["text"]) for page in data["pages"]}


@pytest.mark.parametrize("key", sorted(PROVISIONS))
def test_the_quoted_words_are_on_the_pinned_page(key: str) -> None:
    root = _extracted_text_root()
    if root is None:
        pytest.skip("the corpus's extracted text is not on this machine")
    provision = PROVISIONS[key]
    pages = _pages(root, provision.document[0])
    allowed = " ".join(
        pages[number] for number in range(provision.page, (provision.last_page or provision.page) + 1)
    )
    missing = [fragment for fragment in provision.fragments if _normalise(fragment) not in allowed]
    assert not missing, f"{provision.label} p.{provision.page}: not in the corpus text: {missing}"


def test_every_provision_says_what_it_is_and_where_it_came_from() -> None:
    for provision in PROVISIONS.values():
        source = provision.as_source()
        assert source["section"] == provision.label
        assert source["excerpt"] == provision.quote
        assert source["source_url"].endswith(f"#page={provision.page}")
        assert source["verification_status"] == "verified"
        assert source["current_status"] in {"current", "status_unverified"}


def test_the_catalogue_is_not_empty() -> None:
    """Parametrising over nothing would pass while checking nothing."""
    assert len(PROVISIONS) >= 40
