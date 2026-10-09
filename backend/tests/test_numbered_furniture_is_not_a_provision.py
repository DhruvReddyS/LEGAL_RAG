"""A footnote is not section 4, and a committee list is not section 35.

Chunk boundaries follow the page, not the law, so a numbered list entry
arrives looking exactly like a numbered provision: a leading digit, a full
stop, a short line of text. The section extractor reads that digit as a
section number and the chunk is indexed as "section 4" of whatever Act it sits
in.

Measured against 8,000 indexed chunks of global_legal_corpus_v5: 129 of them
(1.61%) are furniture carrying a section number taken from their own leading
digit. 49 amendment footnotes, 59 numbered person or office lists, 17 form
fields, 3 case-citation footnotes and one "Ibid." Every one of the strings
below was read out of the live index rather than invented.

The harm is not ranking, it is citation. These chunks carry no operative legal
language so they rank poorly, but a section-filtered query for s.4 can return
one, and a citation can then say "section 4" while showing "Address Telephone
Mobile No. E-mail". A false citation presented as proof is worse than no
citation.

The rules are anchored on the chunk's own leading number and bounded by
length, because the standing trade in this classifier runs the other way:
keeping a footnote costs a little precision, deleting a provision costs a
citizen their answer. Every rejection below was checked by printing all 129
and reading them; none is a provision.
"""

from __future__ import annotations

import pytest

from app.ingestion.enrichment import classify_quality


# Verbatim from global_legal_corpus_v5, with the section number it was
# indexed under.
AMENDMENT_FOOTNOTES = [
    ("4. Subs. by Act 24 of 1995, s. 2.", "4"),
    ("1. Ins. by Act 79 of 1971, s. 13.", "1"),
    ("4. Subs. by the A.O. 1937, for “Local Government”.", "4"),
    ("4. Subs. by G.S.R. 1567, dated 20th August, 1968.", "4"),
    ("2. Added by GSR 1011(A), dt. 7.8.1972", "2"),
    ("1. Subs. by SO 1283, dt. 3.5.1963.", "1"),
    ("9. Ins. by Act 25 of 1934, s. 2 and Sch.", "9"),
]

NUMBERED_PERSON_LISTS = [
    ("35. Mr, V.N. Rai, (1.P.S.), DIG Rules, Panchkula.", "35"),
    ("16. Shri Digamber Rana, Dehradun. |", "16"),
    ("1. Justice K. T. Thomas", "1"),
    ("43. Smt. Vimela K. Nambiar : -do-", "43"),
    ("24. Dr. Rakesh Khanna, Professor, Allahabad University, Allahabad.", "24"),
    ("15. Mrs, Billimeria, Navsari.", "15"),
]

FORM_FIELDS = [
    ("4. Address Telephone Mobile No. E-mail", "4"),
    ("6. Place of birth", "6"),
    ("2. E-mail address", "2"),
    ("3. Telephone No.", "3"),
    ("4. Date of birth/age", "4"),
    ("2. Address of the licensee manufacturer", "2"),
]

CASE_CITATIONS = [
    ("2. (1980) 1 SCC 81.", "2"),
    ("8. (1991) 3 SCC 498,", "8"),
    ("9. (1994) 6 SCC 731.", "9"),
]


@pytest.mark.parametrize(("text", "section"), AMENDMENT_FOOTNOTES)
def test_an_amendment_footnote_naming_its_instrument_is_not_a_provision(text, section) -> None:
    """The rule existed and could not fire.

    It required a second marker of "ibid", "w.e.f." or "supra", and almost no
    real footnote carries one -- 49 of the 8,000 indexed chunks are an
    amendment footnote and none of them did. Naming the instrument the
    amendment was made by ("by Act 24 of 1995", "by G.S.R. 1567", "by the
    A.O. 1950") is the same quality of evidence and is what they actually say.
    """
    quality = classify_quality(text, section=section)
    assert quality.quality == "noise"
    assert quality.reason == "amendment_footnote"


@pytest.mark.parametrize(("text", "section"), NUMBERED_PERSON_LISTS)
def test_a_numbered_person_or_office_is_not_a_provision(text, section) -> None:
    quality = classify_quality(text, section=section)
    assert quality.quality == "noise"
    assert quality.reason == "numbered_person_list"


@pytest.mark.parametrize(("text", "section"), FORM_FIELDS)
def test_a_numbered_form_field_is_not_a_provision(text, section) -> None:
    quality = classify_quality(text, section=section)
    assert quality.quality == "noise"
    assert quality.reason == "numbered_form_field"


@pytest.mark.parametrize(("text", "section"), CASE_CITATIONS)
def test_a_numbered_case_citation_is_not_a_provision(text, section) -> None:
    quality = classify_quality(text, section=section)
    assert quality.quality == "noise"
    assert quality.reason == "case_citation_footnote"


def test_a_bare_footnote_reference_is_not_a_provision() -> None:
    quality = classify_quality("7. Ibid.", section="7")
    assert quality.quality == "noise"
    assert quality.reason == "footnote_reference"


# ---------------------------------------------------------------------------
# The far more important direction. Deleting a provision costs a citizen their
# answer, so every rule above is anchored and length-bounded, and these are
# the cases that prove it.
# ---------------------------------------------------------------------------

KEEP = [
    # Short provisions. Operative language keeps them whatever their length.
    ("4. This Act shall come into force at once.", "4"),
    ("2. In this Act, \"vehicle\" means any mechanically propelled conveyance.", "2"),
    ("35. No person shall be arrested without a warrant except as provided.", "35"),
    ("7. Whoever contravenes this section shall be punished with fine.", "7"),
    # A provision that mentions the very words the furniture rules look for.
    # These are the false positives an unanchored rule would create: an
    # earlier measurement counted 779 "furniture" chunks this way, almost all
    # of them long provisions containing "Address" or "Shri".
    (
        "16. Every application shall state the address, telephone number and "
        "e-mail of the applicant, and shall be signed by the person making it.",
        "16",
    ),
    (
        "9. The Director General of Police shall, on receipt of a report, "
        "forward it to the Magistrate having jurisdiction.",
        "9",
    ),
    (
        "3. Subs. by Act 10 of 1950, s. 2, and a person aggrieved by such an "
        "order may appeal to the High Court within thirty days, and the Court "
        "shall dispose of the appeal expeditiously.",
        "3",
    ),
]


@pytest.mark.parametrize(("text", "section"), KEEP)
def test_a_real_provision_is_never_rejected(text, section) -> None:
    assert classify_quality(text, section=section).quality == "indexed"


def test_the_rules_are_anchored_on_the_chunks_own_number() -> None:
    """Mid-text mentions must not match.

    An unanchored version of these patterns matched 700-word provisions that
    happened to contain "Address" or "Shri" somewhere, which would have
    deleted real law at scale.
    """
    mentions = (
        "12. A notice under this section shall be served at the address of "
        "Shri or Smt. as recorded in the register, and the Mobile No. given "
        "in the application shall be used for intimation."
    )
    assert classify_quality(mentions, section="12").quality == "indexed"


def test_a_chunk_long_enough_to_run_into_a_provision_is_kept() -> None:
    """Chunk boundaries do not respect footnotes.

    A chunk can open on an editorial note and carry on into the provision it
    annotates. Every one of the 129 measured furniture chunks is 11 words or
    fewer, so the bound costs nothing real and protects the run-on case.
    """
    run_on = (
        "4. Ins. by Act 8 of 1882, s. 10 and the Collector may thereafter "
        "determine the compensation payable to every interested person under "
        "this Part, after hearing any objection made to him in writing."
    )
    assert classify_quality(run_on, section="4").quality == "indexed"


def test_furniture_without_a_leading_number_is_left_to_the_other_rules() -> None:
    """These rules are about the leading-digit confusion specifically.

    A name or a form field with no number in front of it never acquired a
    bogus section number, so it is not what these rules are for, and the
    length and operative-language rules already handle it.
    """
    assert classify_quality("Shri Digamber Rana, Dehradun.", section=None).quality == "noise"
