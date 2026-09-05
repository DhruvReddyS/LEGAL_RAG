"""Currency must fail closed, and must not fail closed on everything.

Seven guards read `payload["is_superseded"] is True`. Ingestion writes that
field, but it was added after the live index was built, so all 25,517 points
hold `None` -- every guard evaluated false forever while reading as
protective. The same field was matched as `== False` in the retrieval filter,
where `None` is not `False`, so enabling it would have excluded the entire
corpus. One field, treated as a boolean, wrong in both directions at once.
"""

from __future__ import annotations

import pytest

from app.services.currency import CurrencyStatus, resolve_currency


class TestTheThreeAnswers:
    def test_a_curated_act_in_force(self) -> None:
        decision = resolve_currency({"act_name": "The Constitution of India (as on 1 May 2024)"})

        assert decision.status is CurrencyStatus.IN_FORCE
        assert decision.may_ground_a_published_claim
        assert not decision.requires_a_currency_label

    def test_a_repealed_code_is_superseded(self) -> None:
        decision = resolve_currency({"act_name": "The Indian Penal Code Act, 1860"})

        assert decision.status is CurrencyStatus.SUPERSEDED
        assert decision.superseded_by == "The Bharatiya Nyaya Sanhita, 2023"
        assert decision.effective == "2024-07-01"

    def test_an_unknown_authority_is_unverified_not_current(self) -> None:
        """The failure this module exists to remove.

        Absence of information must not read as "in force". Most of the corpus
        is in this state, so getting it wrong is not an edge case.
        """
        decision = resolve_currency({"act_name": "Some Departmental Circular, 2019"})

        assert decision.status is CurrencyStatus.UNVERIFIED
        assert decision.requires_a_currency_label

    def test_an_empty_payload_is_unverified(self) -> None:
        assert resolve_currency({}).status is CurrencyStatus.UNVERIFIED


class TestFailingClosedWithoutAbstainingOnEverything:
    def test_a_repeal_that_saves_prior_conduct_may_still_ground_a_claim(self) -> None:
        """An offence committed on 30 June 2024 is tried under the Penal Code.

        Refusing here would decline to answer about that offence under the law
        that actually governs it -- fail-closed applied so bluntly that it
        produces a wrong answer rather than no answer.
        """
        decision = resolve_currency({"act_name": "The Indian Penal Code Act, 1860"})

        assert decision.may_ground_a_published_claim
        assert decision.saves_prior_conduct
        assert decision.requires_a_currency_label

    def test_a_replacement_with_no_savings_may_not_ground_a_claim(self) -> None:
        """A model manual replaced by a later edition governs no period at
        all, so citing it can only mislead."""
        decision = resolve_currency({"act_name": "Model Prison Manual 2003"})

        assert decision.status is CurrencyStatus.SUPERSEDED
        assert not decision.saves_prior_conduct
        assert not decision.may_ground_a_published_claim

    def test_an_unverified_authority_may_ground_a_labelled_claim(self) -> None:
        """Refusing everything unverified abstains on nearly every question,
        because the corpus cannot verify most of itself."""
        decision = resolve_currency({"act_name": "Advisory on e-FIR to States 13 May 2022"})

        assert decision.status is CurrencyStatus.UNVERIFIED
        assert decision.may_ground_a_published_claim
        assert decision.requires_a_currency_label

    def test_a_stored_supersession_flag_blocks_when_it_is_exactly_true(self) -> None:
        decision = resolve_currency(
            {"act_name": "Unlisted Instrument", "is_superseded": True}
        )

        assert decision.status is CurrencyStatus.SUPERSEDED
        assert not decision.may_ground_a_published_claim

    @pytest.mark.parametrize("value", [None, False, "", 0, "true"])
    def test_anything_other_than_true_is_not_a_supersession(self, value) -> None:
        """`None` means the index predates the field, not that the source is
        current. A truthy string is not a boolean either."""
        decision = resolve_currency(
            {"act_name": "Unlisted Instrument", "is_superseded": value}
        )

        assert decision.status is not CurrencyStatus.SUPERSEDED


class TestPrecedence:
    def test_the_1898_code_resolves_to_the_1973_code(self) -> None:
        """Both the specific and the general rule match this title, and they
        name successors fifty years apart. Longest prefix wins."""
        decision = resolve_currency(
            {"act_name": "The Code of Criminal Procedure, 1898 1996 Accessible"}
        )

        assert decision.superseded_by == "The Code of Criminal Procedure, 1973"
        assert decision.effective == "1974-04-01"

    def test_the_1973_code_resolves_to_the_sanhita(self) -> None:
        decision = resolve_currency(
            {"act_name": "The Code of Criminal Procedure, 1973 (Act No.2 of 1974)"}
        )

        assert decision.superseded_by == "The Bharatiya Nagarik Suraksha Sanhita, 2023"

    def test_a_document_about_a_repealed_act_is_not_itself_repealed(self) -> None:
        """An advisory on section 498A is operative guidance. Marking it
        repealed would put a false warning on law that still applies."""
        decision = resolve_currency(
            {"act_name": "Advisory on measures to curb misuse of section 498A IPC"}
        )

        assert decision.status is not CurrencyStatus.SUPERSEDED

    def test_private_case_evidence_has_no_statutory_currency(self) -> None:
        decision = resolve_currency(
            {"corpus_scope": "private_case", "title": "witness-statement.txt"}
        )

        assert decision.status is CurrencyStatus.UNVERIFIED
        assert decision.source == "private_case"


class TestTheRetrievalFilterIsTriState:
    def test_excluding_superseded_excludes_only_an_explicit_true(self) -> None:
        """Matching `is_superseded == False` excluded every point in the live
        collection, where all 25,517 hold None. The filter means "not known to
        be superseded"."""
        from app.services.retrieval import RetrievalFilters

        query_filter = RetrievalFilters(exclude_superseded=True, corpus_tiers=[]).to_qdrant()

        assert query_filter is not None
        assert query_filter.must_not is not None
        conditions = [c for c in query_filter.must_not if getattr(c, "key", None) == "is_superseded"]
        assert len(conditions) == 1
        assert conditions[0].match.value is True

        positive = [
            c
            for c in (query_filter.must or [])
            if getattr(c, "key", None) == "is_superseded"
        ]
        assert not positive, "a positive match on this field excludes the whole corpus"

    def test_the_filter_is_off_by_default(self) -> None:
        from app.services.retrieval import RetrievalFilters

        assert RetrievalFilters().exclude_superseded is False
