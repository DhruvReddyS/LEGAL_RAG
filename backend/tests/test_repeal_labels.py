"""Two labels, because they say different things about different documents.

Label A -- this document is no longer in force -- belongs to the repealed Act.
Label B -- this document concerns a provision that has moved -- belongs to the
SOPs, circulars and judgments written against the old numbering. Those are
themselves operative, and marking them out of force would be false in a way a
police reader spots immediately.

The motivating failure: "can you help me now with the FIR procedure" cited
*Amendment in Section 154 of the Code of Criminal Procedure* with no marker,
because the repeal rule matches names that *begin* with a repealed code. The
wrong fix was to loosen that match.
"""

from __future__ import annotations

import pytest

from app.services.repeal_labels import RepealLabel, repeal_notice
from app.services.section_mapping import (
    map_citation,
    map_citations,
    map_section,
    map_sections,
    resolve_code,
)


class TestLabelAIsTheAuthorityItself:
    def test_a_repealed_act_is_marked_out_of_force(self) -> None:
        notice = repeal_notice(
            {
                "act_name": "The Indian Penal Code Act, 1860",
                "source_type": "ACT",
                "text": "Whoever commits theft shall be punished.",
            }
        )

        assert notice.label is RepealLabel.NO_LONGER_IN_FORCE
        assert notice.replaced_by == "The Bharatiya Nyaya Sanhita, 2023"
        assert notice.repealed_on == "2024-07-01"

    def test_a_replacement_act_carries_no_label(self) -> None:
        notice = repeal_notice(
            {
                "act_name": "THE BHARATIYA NAGARIK SURAKSHA SANHITA, 2023",
                "source_type": "ACT",
                "text": "173. Information in cognizable cases.",
            }
        )

        assert notice.label is RepealLabel.NONE


class TestLabelBIsMaterialAboutTheAuthority:
    def test_the_motivating_case_now_carries_a_label(self) -> None:
        notice = repeal_notice(
            {
                "act_name": "Amendment in Section 154 of The Code of Criminal procedure",
                "source_type": "GOVERNMENT_GUIDANCE",
                "text": (
                    "The officer shall register an FIR under section 154 of the "
                    "Code of Criminal Procedure without delay."
                ),
            }
        )

        assert notice.label is RepealLabel.CONCERNS_REPEALED_PROVISION
        assert notice.mappings
        mapping = notice.mappings[0]
        assert (mapping.from_code, mapping.from_section) == ("CrPC", "154")
        assert (mapping.to_code, mapping.to_section) == ("BNSS", "173")

    def test_an_operative_circular_is_not_marked_out_of_force(self) -> None:
        """The direction that must never regress.

        An advisory on section 498A still binds. Label A here would tell a
        police reader to disregard guidance that is in force.
        """
        notice = repeal_notice(
            {
                "act_name": "Advisory on measures to curb misuse of section 498A IPC",
                "source_type": "GOVERNMENT_GUIDANCE",
                "text": "States shall ensure section 498A IPC is not misused.",
            }
        )

        assert notice.label is not RepealLabel.NO_LONGER_IN_FORCE
        assert notice.label is RepealLabel.CONCERNS_REPEALED_PROVISION

    def test_a_judgment_on_a_moved_provision_is_labelled(self) -> None:
        notice = repeal_notice(
            {
                "act_name": "Arjun Panditrao Khotkar vs Kailash Kushanrao",
                "source_type": "SUPREME_COURT_JUDGMENT",
                "text": "A certificate under section 65B of the Indian Evidence Act is mandatory.",
            }
        )

        assert notice.label is RepealLabel.CONCERNS_REPEALED_PROVISION
        assert notice.mappings[0].to_section == "63"
        assert notice.has_ingredient_changes

    def test_guidance_citing_nothing_repealed_carries_no_label(self) -> None:
        notice = repeal_notice(
            {
                "act_name": "Advisory on e-FIR to States",
                "source_type": "GOVERNMENT_GUIDANCE",
                "text": "States should deploy the e-FIR portal in every district.",
            }
        )

        assert notice.label is RepealLabel.NONE

    def test_an_in_force_act_citing_another_act_needs_no_label(self) -> None:
        """Label B is for material *about* the law, not for statute text."""
        notice = repeal_notice(
            {
                "act_name": "THE BHARATIYA NAGARIK SURAKSHA SANHITA, 2023",
                "source_type": "ACT",
                "text": "Nothing in section 154 of the Code of Criminal Procedure shall apply.",
            }
        )

        assert notice.label is RepealLabel.NONE

    def test_a_cited_provision_with_no_known_mapping_is_named_not_hidden(self) -> None:
        """Silence would read as "unchanged", which is the wrong default."""
        notice = repeal_notice(
            {
                "act_name": "Circular on an obscure provision",
                "source_type": "GOVERNMENT_GUIDANCE",
                "text": "Officers shall comply with section 874 of the Indian Penal Code.",
            }
        )

        assert notice.label is RepealLabel.CONCERNS_REPEALED_PROVISION
        assert notice.unmapped_provisions == ("IPC s.874",)
        assert not notice.mappings


class TestTheSectionMapper:
    @pytest.mark.parametrize(
        ("act", "section", "expected_code", "expected_section"),
        [
            ("Code of Criminal Procedure", "154", "BNSS", "173"),
            ("IPC", "302", "BNS", "103"),
            ("Indian Evidence Act", "65B", "BSA", "63"),
        ],
    )
    def test_forward(self, act, section, expected_code, expected_section) -> None:
        found = map_citations(act, section)

        assert found
        assert {m.to_code for m in found} == {expected_code}
        assert expected_section in {str(m.to_section).split("(")[0] for m in found}

    def test_both_directions_come_from_the_source_not_from_inversion(self) -> None:
        """This used to assert the reverse was *derived* from the forward.

        That was wrong, and the official tables show why: one provision
        frequently replaces several, so inverting a forward pair invents a
        one-to-one correspondence the Act never made. Both directions are
        now read from the published tables, and the test asserts they agree
        rather than that one was computed from the other.
        """
        forward = map_sections("IPC", "302")
        backward = map_sections("BNS", "103")

        assert forward and backward
        assert "103" in {str(m.to_section).split("(")[0] for m in forward}
        assert "302" in {str(m.to_section).split("(")[0] for m in backward}
        assert {m.to_code for m in backward} == {"IPC"}

    def test_an_unmapped_section_returns_nothing_rather_than_a_guess(self) -> None:
        """The table is partial on purpose. A gap is visible; a guess is not."""
        assert map_section("IPC", "999") is None

    def test_sedition_was_not_re_enacted_and_is_not_mapped_to_bns_152(self) -> None:
        """The pair that justifies using the official table.

        The model-authored concordance this replaced said IPC s.124A is now
        BNS s.152. That is the equivalence repeated across commentary and
        the press, and it is wrong: the official NCRB table records s.124A
        as deleted, and BNS s.152 is a separate offence with different
        elements and a different threshold. A reviewer asked to check fifty
        plausible mappings would have approved this one.

        So the answer is neither "BNS s.152" nor silence. It is that the
        provision was not carried forward, which the table knows and says.
        """
        found = map_sections("IPC", "124A")

        assert len(found) == 1
        assert found[0].to_section is None
        assert not found[0].has_successor
        assert not found[0].is_renumbering
        # Not the same as an unknown provision, which returns nothing at all.
        assert map_sections("IPC", "874") == ()

    def test_a_changed_provision_is_marked_from_the_source_table(self) -> None:
        """(Change) in the official table means the provision was altered,
        not merely renumbered, and a reader who assumes equivalence gets the
        elements wrong."""
        changed = [m for m in map_sections("IPC", "278") if m.ingredients_changed]

        assert changed, "IPC s.278 is marked (Change) in the NCRB table"
        assert not changed[0].is_renumbering

    def test_one_provision_replacing_several_is_not_narrowed_to_one(self) -> None:
        """BNS s.179 stands in for eleven IPC sections.

        Returning one of them would assert a correspondence far narrower
        than the Act makes, and the reader would have no way to see the
        other ten.
        """
        found = map_sections("BNS", "179")

        assert len(found) > 5
        assert {m.to_section for m in found} >= {"237", "238", "489B"}
        # map_section refuses rather than picking one of eleven arbitrarily.
        assert map_section("BNS", "179") is None

    @pytest.mark.parametrize(
        ("written", "expected"),
        [
            ("s. 154", "BNSS"),
            ("Section 154", "BNSS"),
            ("154.", "BNSS"),
            ("u/s 154", "BNSS"),
        ],
    )
    def test_section_numbers_are_normalised(self, written, expected) -> None:
        found = map_sections("CrPC", written)

        assert found
        assert {m.to_code for m in found} == {expected}

    def test_subsections_are_distinct_provisions(self) -> None:
        """303(1) defines theft and 303(2) punishes it. Collapsing them would
        answer a question about punishment with a definition."""
        definition = map_sections("BNS", "303(1)")
        punishment = map_sections("BNS", "303(2)")

        assert definition and punishment
        assert {m.to_section for m in definition} == {"378"}
        assert {m.to_section for m in punishment} == {"379"}

    def test_the_longest_code_alias_wins(self) -> None:
        """"code of criminal procedure" must not be shadowed by a shorter
        alias that appears inside it."""
        assert resolve_code("The Code of Criminal Procedure, 1973") == "CrPC"
        assert resolve_code("Bharatiya Nagarik Suraksha Sanhita") == "BNSS"

    def test_the_table_declares_where_it_came_from(self) -> None:
        """Provenance has to travel with the mapping, whichever way it cuts.

        When the table was model-authored this asserted
        'pending_legal_review', so that nothing could present it as settled
        law. It is now built from the NCRB tables and says so. The property
        being defended is the same one: a consumer can always find out what
        kind of thing it is holding.
        """
        mapping = map_section("IPC", "302")

        assert mapping is not None
        assert mapping.review_status == "official_source"


class TestTheOfficialTableNeedsReconciling:
    """The source is printed for reading, not for parsing, and says two
    contradictory things in places. Both rules below decide which wins, and
    both decide in the direction that cannot mislead."""

    def test_a_provision_with_a_successor_is_never_reported_as_dropped(self) -> None:
        """IEA s.65B is the real case.

        A wrapped continuation line in the NCRB table carries "Deleted"
        against text belonging to the row above, so s.65B appears both
        mapped to BSA s.63 and not re-enacted. Reporting a live provision
        as repealed is the more damaging of the two errors, so the
        successor wins.
        """
        found = map_sections("IEA", "65B")

        assert found
        assert all(m.has_successor for m in found)
        assert "63" in {str(m.to_section).split("(")[0] for m in found}

    def test_a_section_without_a_subsection_matches_all_of_its_subsections(self) -> None:
        """The BNSS concordance is printed at sub-section level.

        Exact matching alone returned nothing at all for "BNSS s.35" and
        "BNSS s.173" -- the arrest power and the FIR provision, the two most
        cited sections in this corpus. Someone who writes "s.35" means the
        section, and the section is all of its sub-sections.
        """
        arrest = map_sections("BNSS", "35")
        fir = map_sections("BNSS", "173")

        assert arrest and fir
        assert "41" in {str(m.to_section).split("(")[0] for m in arrest}
        assert "154" in {str(m.to_section).split("(")[0] for m in fir}

    def test_a_subsection_that_is_absent_does_not_fall_back(self) -> None:
        """Asking for 35(9) must not quietly answer about 35(1).

        The fallback widens a section-level citation to its sub-sections.
        Running it in the other direction would answer a specific question
        with a different provision's mapping.
        """
        assert map_sections("BNSS", "35(9)") == ()

    def test_the_fallback_is_ordered_deterministically(self) -> None:
        """The order is pinned, not merely self-consistent.

        The first version of this test compared two calls to each other.
        That passes whatever the ordering is, because _load is cached and
        both calls walk the same dict in the same process -- it certified
        the behaviour instead of protecting it, and the mutation that
        removed the sort did not fail it.

        The fallback collects across dict keys, so without an explicit sort
        the order follows insertion and would shift whenever the table is
        rebuilt. Callers show the first counterpart to the reader, so a
        shuffle changes the answer.
        """
        assert [(m.from_section, m.to_section) for m in map_sections("BNSS", "35")] == [
            ("35(1)", "41"),
            ("35(2)", "41(2)"),
            ("35(6)", "41A"),
        ]


class TestNotReEnactedReachesTheNotice:
    def test_a_dropped_provision_is_reported_separately_from_an_unknown_one(self) -> None:
        """"The new code dropped this" and "this table has not heard of it"
        are different answers. Merging them turns a positive finding into a
        gap, and a gap reads as "probably fine"."""
        notice = repeal_notice(
            {
                "act_name": "Circular on sedition",
                "source_type": "GOVERNMENT_GUIDANCE",
                "text": "See section 124A of the Indian Penal Code and section 874 of the Indian Penal Code.",
            }
        )

        assert notice.not_re_enacted == ("IPC s.124A",)
        assert notice.unmapped_provisions == ("IPC s.874",)
        assert not notice.mappings
