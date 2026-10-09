"""A PDF with two text layers emits every word twice, and the result is unsearchable.

    JananiJanani ShishuShishu SurakshaSuraksha KaryakramKaryakram

The damage is not cosmetic. "JananiJanani" cannot match a query for "Janani",
so the passage sits in the index and cannot be reached -- a coverage hole the
workflow audit still counts as `canonical_complete`, because the document is
in the manifest and nothing measures whether its text survived extraction.

Measured against the whole of global_legal_corpus_v5, 43,577 indexed chunks:
36 are like this (0.08%), concentrated in three documents -- the Child
Helpline standard operating procedure (25 chunks), the victim care and support
scheme (10) and the NALSA community mediation SOP (1). Every rejection was
printed and read at the lowest ratios; none is real text.

They are also the longest chunks in the corpus, which is what pushes a
single-item batch past the accelerator's memory and forces the whole document
onto the CPU. Rejecting them is both a quality and a throughput fix.

Rejected rather than repaired: de-duplicating the words would recover the
content and would also be a silent rewrite of stored legal text on a
heuristic. Re-extracting the three documents is the fix that actually recovers
them, and rejection is what makes the need visible.
"""

from __future__ import annotations

import pytest

from app.ingestion.enrichment import classify_quality, doubled_word_ratio


# Verbatim from global_legal_corpus_v5.
DOUBLED = [
    "a.a. JananiJanani ShishuShishu SurakshaSuraksha KaryakramKaryakram b.b. "
    "PradhanPradhan MantriMantri MatruMatru VandanaVandana YojanaYojana",
    "5.5. HUMANHUMAN RESOURCERESOURCE States/UTsStates/UTs asas perper theirtheir "
    "populationpopulation havehave beenbeen allocatedallocated",
    "jointlyjointly withwith herher guardian.guardian. DCPUDCPU willwill ensureensure "
    "thatthat thethe childchild isis producedproduced beforebefore",
    "lost/foundlost/found andand | FollowFollow upup callscalls identifiedidentified "
    "byby thethe CounsellorCounsellor forfor furtherfurther actionaction",
]

# Real legal text, including a case that names the very scheme above. The
# words repeat across the passage; no word is its own doubling.
REAL = [
    "The Janani Shishu Suraksha Karyakram shall provide free delivery and "
    "caesarean section services to every pregnant woman attending a public "
    "health institution.",
    "Whoever dishonestly takes any movable property out of the possession of "
    "any person without that person's consent shall be punished.",
    "A police officer shall not arrest a person without a warrant except in "
    "the cases provided by this section, and shall record the grounds.",
    "The State Government may, by notification, make rules to carry out the "
    "purposes of this Act, and every such rule shall be laid before the "
    "State Legislature.",
]


@pytest.mark.parametrize("text", DOUBLED)
def test_a_doubled_text_layer_is_not_indexed(text: str) -> None:
    quality = classify_quality(text, section="5")
    assert quality.quality == "noise"
    assert quality.reason == "doubled_text_layer"


@pytest.mark.parametrize("text", REAL)
def test_real_legal_text_is_never_rejected(text: str) -> None:
    """The direction that matters. Deleting a provision costs a citizen an answer."""
    assert classify_quality(text, section="5").quality == "indexed"
    assert doubled_word_ratio(text) == 0.0


def test_a_passage_naming_a_doubled_scheme_is_kept() -> None:
    """The nearest miss.

    The worst offender in the corpus is a Child Helpline SOP about the Janani
    Shishu Suraksha Karyakram. A real provision about the same scheme shares
    every word with it and must survive.
    """
    real = REAL[0]
    assert "Janani Shishu Suraksha Karyakram" in real
    assert classify_quality(real, section="2").quality == "indexed"


def test_one_doubled_word_is_not_a_pattern() -> None:
    """Reduplication happens. A ratio needs a sample to be a ratio."""
    occasional = (
        "The Committee shall meet and the the Chairperson shall preside over "
        "every sitting convened under this regulation for the stated purpose."
    )
    assert doubled_word_ratio(occasional) < 0.30
    assert classify_quality(occasional, section="3").quality == "indexed"


def test_a_short_passage_is_not_judged_on_a_ratio() -> None:
    """Below the sample floor the ratio is meaningless, so it is not consulted."""
    assert doubled_word_ratio("TheThe officerofficer") == 0.0


def test_the_threshold_sits_between_what_was_measured() -> None:
    """Measured: real text scores 0%, the 36 rejected chunks score 30% to 91%.

    The gap is wide, so the threshold is not finely tuned -- which is the
    point. A rule that needed tuning to this corpus would not survive the next
    one.
    """
    from app.ingestion.enrichment import _DOUBLED_WORD_MINIMUM_RATIO

    assert 0.20 <= _DOUBLED_WORD_MINIMUM_RATIO <= 0.50
    assert max(doubled_word_ratio(text) for text in REAL) == 0.0
    assert min(doubled_word_ratio(text) for text in DOUBLED) >= _DOUBLED_WORD_MINIMUM_RATIO
