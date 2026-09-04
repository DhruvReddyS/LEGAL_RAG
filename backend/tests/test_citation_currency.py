"""What the reader is told about whether a source is still law.

21.1% of the corpus is the Indian Penal Code, the Code of Criminal Procedure
and the Indian Evidence Act, repealed on 1 July 2024. Their replacements are
4%. Repealed law outnumbers current law five to one, so without this a citizen
asking about criminal law is answered from provisions that no longer apply,
with nothing on the page to say so.
"""

from __future__ import annotations

from app.services.citation_status import citation_currency


class TestRepealedIsNotSuperseded:
    def test_a_repealed_act_is_labelled_and_names_its_successor(self) -> None:
        status, replaced_by, repealed_on = citation_currency(
            {
                "act_name": "The Indian Penal Code Act, 1860",
                "replaced_by": "The Bharatiya Nyaya Sanhita, 2023",
                "repealed_on": "2024-07-01",
            }
        )

        assert status == "repealed"
        assert replaced_by == "The Bharatiya Nyaya Sanhita, 2023"
        assert repealed_on == "2024-07-01"

    def test_superseded_still_outranks_repealed(self) -> None:
        """They mean different things and must not be conflated.

        `superseded` means the source cannot ground a published claim at all.
        `repealed` means the Act no longer applies to new conduct but still
        governs conduct from before the repeal, so it is cited with a warning
        rather than withheld. A source marked both is the stricter one.
        """
        status, _, _ = citation_currency(
            {"is_superseded": True, "replaced_by": "The Bharatiya Nyaya Sanhita, 2023"}
        )

        assert status == "superseded"

    def test_an_in_force_act_is_unchanged(self) -> None:
        status, replaced_by, repealed_on = citation_currency({"is_current": True})

        assert status == "current"
        assert replaced_by is None
        assert repealed_on is None

    def test_an_unverified_source_is_still_unverified(self) -> None:
        """The corpus marks every document's currency as needing verification,
        so this is the common case and must not silently become 'current'."""
        status, _, _ = citation_currency({"is_current": False})

        assert status == "status_unverified"

    def test_private_case_evidence_is_not_applicable(self) -> None:
        status, _, _ = citation_currency({"corpus_scope": "private_case"})

        assert status == "not_applicable"

    def test_an_empty_string_successor_is_not_a_repeal(self) -> None:
        """Payload fields arrive as '' rather than None often enough that
        truthiness, not presence, has to decide this."""
        status, replaced_by, _ = citation_currency({"replaced_by": "", "repealed_on": ""})

        assert status == "status_unverified"
        assert replaced_by is None
