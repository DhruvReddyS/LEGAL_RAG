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
from app.services.section_mapping import map_citation, map_section, resolve_code


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
                "text": "Officers shall comply with section 295 of the Indian Penal Code.",
            }
        )

        assert notice.label is RepealLabel.CONCERNS_REPEALED_PROVISION
        assert notice.unmapped_provisions == ("IPC s.295",)
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
        mapping = map_citation(act, section)

        assert mapping is not None
        assert (mapping.to_code, mapping.to_section) == (expected_code, expected_section)

    def test_the_reverse_direction_is_derived_not_typed_twice(self) -> None:
        """Two hand-written directions drift apart. One fact, read both ways."""
        forward = map_section("IPC", "302")
        backward = map_section("BNS", "103")

        assert forward is not None and backward is not None
        assert backward.to_code == "IPC"
        assert backward.to_section == "302"
        assert backward.subject == forward.subject
        assert backward.ingredients_changed == forward.ingredients_changed

    def test_an_unmapped_section_returns_nothing_rather_than_a_guess(self) -> None:
        """The table is partial on purpose. A gap is visible; a guess is not."""
        assert map_section("IPC", "999") is None

    def test_a_changed_offence_is_not_presented_as_a_renumbering(self) -> None:
        """Sedition is the case that matters. BNS s.152 is a differently framed
        offence, and treating it as IPC s.124A renumbered gets the elements
        wrong."""
        mapping = map_section("IPC", "124A")

        assert mapping is not None
        assert mapping.to_section == "152"
        assert mapping.ingredients_changed
        assert not mapping.is_renumbering
        assert mapping.note

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
        mapping = map_section("CrPC", written)

        assert mapping is not None
        assert mapping.to_code == expected

    def test_subsections_are_distinct_provisions(self) -> None:
        """303(1) defines theft and 303(2) punishes it. Collapsing them would
        answer a question about punishment with a definition."""
        definition = map_section("BNS", "303(1)")
        punishment = map_section("BNS", "303(2)")

        assert definition is not None and punishment is not None
        assert definition.to_section == "378"
        assert punishment.to_section == "379"

    def test_the_longest_code_alias_wins(self) -> None:
        """"code of criminal procedure" must not be shadowed by a shorter
        alias that appears inside it."""
        assert resolve_code("The Code of Criminal Procedure, 1973") == "CrPC"
        assert resolve_code("Bharatiya Nagarik Suraksha Sanhita") == "BNSS"

    def test_the_table_declares_that_it_is_unreviewed(self) -> None:
        """A model-authored concordance presented as settled law is exactly
        the confident error this system exists to avoid."""
        mapping = map_section("IPC", "302")

        assert mapping is not None
        assert mapping.review_status == "pending_legal_review"
