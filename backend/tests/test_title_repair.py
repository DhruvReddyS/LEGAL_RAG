"""Title repair must remove listing furniture and nothing else.

An earlier version of this script also stripped a trailing year when the title
named another year elsewhere. That turned "Transgender Persons (Protection of
Rights) Rules, 2020" into "Rules" and "(Prevention of Atrocities) Act, 1989"
into "Act" - destroying more meaning than the artefact ever did. In an Indian
legal title the year is part of the name.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from repair_document_titles import clean_title  # noqa: E402


@pytest.mark.parametrize(
    ("dirty", "expected"),
    [
        (
            "The Code of Criminal Procedure, 1973 (Act No.2 of 1974) 1996 "
            "Accessible_Vol_01(PDF 4.15MB) | Accessible_Vol_02(PDF 3.42MB)",
            "The Code of Criminal Procedure, 1973 (Act No.2 of 1974) 1996",
        ),
        (
            "Women in Custody 1989 Accessible_(PDF 6.00MB) | Accessible_Hindi(PDF 7.86MB)",
            "Women in Custody 1989",
        ),
        (
            "Section 44, Code of Criminal Procedure, 1898 1967 Accessible_(PDF 2.81MB)",
            "Section 44, Code of Criminal Procedure, 1898 1967",
        ),
        (
            "Model Prison Manual Accessible_Part_1( 6.81MB) | Accessible_Part_2( 6.67MB)",
            "Model Prison Manual",
        ),
        ("Some Advisory 250883_english_01042024.pdf", "Some Advisory"),
    ],
)
def test_listing_furniture_is_removed(dirty: str, expected: str) -> None:
    assert clean_title(dirty) == expected


@pytest.mark.parametrize(
    "title",
    [
        # The year is the title. None of these may lose it.
        "Transgender Persons (Protection of Rights) Rules, 2020",
        "The Scheduled Castes and the Scheduled Tribes (Prevention of Atrocities) Act, 1989",
        "The Bharatiya Nagarik Suraksha Sanhita, 2023",
        "The Indian Evidence Act, 1872",
        "Protection of Children from Sexual Offences Act, 2012",
        # Long official titles are names, not padding, and are not truncated.
        "Advisory on measures to be taken by States UTs to curb of misuse of "
        "section 498-A of the Indian Penal Code-reg",
        # Ordinary text containing a number must be untouched.
        "Guidelines for Implementation of the Modernisation of Prisons Project",
    ],
)
def test_a_clean_title_is_left_exactly_alone(title: str) -> None:
    assert clean_title(title) == title


def test_repair_never_empties_a_title() -> None:
    """Falling back to the original beats publishing a citation with no name."""
    assert clean_title("Accessible_(PDF 1.00MB)") == "Accessible_(PDF 1.00MB)"


def test_every_manifest_title_survives_repair_non_empty() -> None:
    from repair_document_titles import load

    for document in load():
        original = document.get("title") or ""
        if not original:
            continue
        cleaned = clean_title(original)
        assert cleaned.strip(), original
        # Repair only ever removes; it must not invent text.
        assert len(cleaned) <= len(original), original
