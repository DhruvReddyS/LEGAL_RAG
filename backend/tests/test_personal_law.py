"""A marriage question is shown the marriage law of the community it is about.

Measured on ILSIC's layperson questions: of 117 held-out questions labelled with
the Hindu Marriage Act, 53 were shown another community's marriage law, because
the communities' divorce sections share their wording. "We are Christians. How
do we get a divorce?" was shown neither the Divorce Act, 1869 nor anything else
of use, and "We are Parsis..." was shown HMA s.13B.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.citation_following import implementation_provisions_for_query
from app.services.fast_research import shown_to_the_reader
from app.services.personal_law import (
    CHRISTIAN,
    HINDU,
    MUSLIM,
    PARSI,
    SPECIAL,
    governing_communities,
    marriage_law_community,
    unasked_personal_law,
)


def _hit(chunk_id: str, act: str, section: str = "1") -> SimpleNamespace:
    return SimpleNamespace(
        payload={
            "chunk_id": chunk_id,
            "act_name": act,
            "title": act,
            "section": section,
            "canonical_document_id": f"doc-{chunk_id}",
        },
        fused_score=0.5,
        dense_score=None,
        sparse_score=None,
    )


HMA = _hit("hma", "The Hindu Marriage Act, 1955", "13")
IDA = _hit("ida", "The Divorce Act, 1869", "10")
PMDA = _hit("pmda", "The Parsi Marriage and Divorce Act, 1936")
SMA = _hit("sma", "The Special Marriage Act, 1954", "27")
DMMA = _hit("dmma", "The Dissolution of Muslim Marriages Act, 1939", "2")
DV = _hit("dv", "The Protection of Women from Domestic Violence Act, 2005", "12")
MARRIAGE_LAWS = [HMA, IDA, PMDA, SMA, DMMA, DV]


def _kept(query: str) -> set[str]:
    unasked = unasked_personal_law(query, MARRIAGE_LAWS)
    return {hit.payload["chunk_id"] for hit in MARRIAGE_LAWS} - unasked


class TestWhichCommunity:
    @pytest.mark.parametrize(
        ("question", "expected"),
        [
            ("My wife left me. Can I get a divorce?", {HINDU}),
            ("We are Christians. How do we get a divorce?", {CHRISTIAN}),
            ("We are Parsis and want a divorce by mutual consent.", {PARSI}),
            ("My husband gave me triple talaq over the phone", {MUSLIM}),
            ("We had a court marriage. How do we divorce?", {SPECIAL}),
            # A marriage under the Special Marriage Act is governed by it whatever the religion.
            ("I married a Muslim man in a court marriage and want a divorce.", {SPECIAL}),
            ("I am Hindu and my wife is Christian. Which law applies to our divorce?", {HINDU, CHRISTIAN}),
        ],
    )
    def test_the_named_community_governs(self, question: str, expected: set[str]) -> None:
        assert governing_communities(question) == expected

    def test_acts_are_recognised_by_name_and_the_parsi_act_is_not_the_divorce_act(self) -> None:
        assert marriage_law_community(IDA.payload) == CHRISTIAN
        assert marriage_law_community(PMDA.payload) == PARSI
        assert marriage_law_community(HMA.payload) == HINDU
        assert marriage_law_community(DV.payload) is None


class TestWhatIsShown:
    def test_a_question_naming_no_community_keeps_the_hindu_marriage_act(self) -> None:
        assert _kept("How do I divorce my husband for cruelty?") == {"hma", "dv"}

    def test_a_christian_question_drops_the_hindu_marriage_act(self) -> None:
        assert _kept("We are Christians. How do we get a divorce?") == {"ida", "dv"}

    def test_a_parsi_question_is_not_shown_hma_mutual_consent(self) -> None:
        assert _kept("We are Parsis and want a divorce by mutual consent.") == {"pmda", "dv"}

    def test_laws_that_are_not_marriage_laws_stay(self) -> None:
        assert "dv" in _kept("My husband beats me. Can I get protection and a divorce?")

    def test_a_question_that_is_not_about_marriage_is_untouched(self) -> None:
        assert unasked_personal_law("What is the punishment for theft?", MARRIAGE_LAWS) == frozenset()

    def test_the_lane_applies_it_to_every_source_it_shows(self) -> None:
        shown = shown_to_the_reader(
            [SMA, PMDA], [], [HMA], limit=3, query="We are Christians and want a divorce."
        )
        assert shown == []
        shown = shown_to_the_reader(
            [SMA, PMDA], [], [IDA], limit=3, query="We are Christians and want a divorce."
        )
        assert [hit.payload["chunk_id"] for hit in shown] == ["ida"]


def _linked(question: str) -> set[tuple[str, str]]:
    return {provision.key for provision in implementation_provisions_for_query(question)}


class TestLinkedSections:
    @pytest.mark.parametrize(
        ("question", "expected"),
        [
            ("My wife left me and won't come back. Can I get a divorce?", {("HMA", "13"), ("HMA", "9")}),
            ("We both want a divorce by mutual consent", {("HMA", "13B")}),
            ("We are Christians. How do we get a divorce?", {("IDA", "10")}),
            ("I am a Catholic and want judicial separation", {("IDA", "22")}),
            ("We had a court marriage and now want a divorce", {("SMA", "27")}),
            ("Our interfaith marriage is over; can we get a mutual divorce?", {("SMA", "28")}),
            ("I am a Muslim woman and want a divorce from my husband", {("DMMA", "2")}),
            ("We are Parsis and want a divorce", {("PMDA", "32")}),
            ("We are Parsis and want a divorce by mutual consent.", {("PMDA", "32B")}),
            ("My Parsi husband deserted me and will not come back", {("PMDA", "36")}),
        ],
    )
    def test_each_community_reaches_its_own_sections(
        self, question: str, expected: set[tuple[str, str]]
    ) -> None:
        marriage = {key for key in _linked(question) if key[0] in {"HMA", "IDA", "SMA", "DMMA", "PMDA"}}
        assert marriage == expected

    @pytest.mark.parametrize(
        "question",
        [
            "We are Christians. How do we get a divorce?",
            "We are Parsis and want a divorce by mutual consent.",
            "I married a Muslim man in a court marriage and want a divorce.",
        ],
    )
    def test_the_hindu_marriage_act_stands_down_for_another_community(self, question: str) -> None:
        assert not any(code == "HMA" for code, _ in _linked(question))

    def test_a_court_marriage_is_not_sent_to_muslim_or_christian_law(self) -> None:
        linked = _linked("I married a Muslim man in a court marriage and want a divorce.")
        assert ("SMA", "27") in linked
        assert not any(code in {"DMMA", "IDA"} for code, _ in linked)
