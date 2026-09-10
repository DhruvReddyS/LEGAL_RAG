"""Which query term is required to appear in a passage.

The rule is that a question's rarest term carries its topic, so a passage
lacking it is not about the question. That holds for the terms that mark a
corpus gap -- landlord 37 chunks, noise 16, consumer 25, visa 25 -- and it is
what lets the system decline a question it has no source for.

It breaks in two ways on how citizens actually write, and both were measured
declining answerable questions rather than gaps.
"""

from __future__ import annotations

from app.services.fast_research import _focus_tokens
from app.services.retrieval import _base_forms, _distinctive_from_counts


class TestAnAbsentTermIsRequired:
    def test_a_term_the_corpus_never_contains_wins_outright(self) -> None:
        """The strongest signal that a question is outside the corpus."""
        assert _distinctive_from_counts(
            {"visa": 0, "requirements": 481, "canada": 123}
        ) == ["visa"]

    def test_otherwise_the_rarest_band_is_required(self) -> None:
        assert _distinctive_from_counts({"landlord": 37, "deposit": 152}) == [
            "landlord"
        ]

    def test_no_terms_require_nothing(self) -> None:
        assert _distinctive_from_counts({}) == []


class TestColloquialWordsAreNotTopics:
    """A statute says "any person"; a citizen says "someone".

    Indefinite pronouns are therefore *rare* in a legal corpus, which made the
    rarest-term rule seize on them. Measured: "someone" appears in 90 chunks
    and became the required term for "when can the police arrest someone
    without a warrant", rejecting the correct BNSS passage at 0.80 coverage --
    and every other passage, so the question was declined outright.
    """

    def test_someone_is_not_a_focus_term(self) -> None:
        assert "someone" not in _focus_tokens(
            "When can the police arrest someone without a warrant?"
        )

    def test_the_legal_terms_of_that_question_survive(self) -> None:
        """Over-filtering here is the opposite failure: strip the topic words
        and every passage matches, which is how a gap gets answered."""
        focus = _focus_tokens("When can the police arrest someone without a warrant?")

        assert {"arrest", "warrant", "police"} <= focus

    def test_light_verbs_are_dropped(self) -> None:
        focus = _focus_tokens("What protections does the law give children?")

        assert "give" not in focus
        assert {"protections", "children"} <= focus

    def test_citizen_request_wording_does_not_become_the_legal_topic(self) -> None:
        focus = _focus_tokens(
            "How do I file a workplace harassment complaint and what is the deadline?"
        )

        assert not {"file", "deadline"} & focus
        assert {"workplace", "harassment", "complaint"} <= focus


class TestARareInflectionIsNotAGap:
    """ "protections" appears in 35 chunks, "protection" in thousands.

    Counted alone the plural looks as rare as a genuinely absent topic --
    rarer, in fact, than "landlord" at 37 -- so it was required, and every
    passage about the protection of children was rejected. Frequency is
    therefore taken across a term's spellings.
    """

    def test_a_plural_resolves_to_its_singular(self) -> None:
        assert _base_forms("protections") == ("protection",)
        assert _base_forms("rights") == ("right",)

    def test_a_sibilant_plural_drops_only_es(self) -> None:
        assert _base_forms("witnesses") == ("witness",)
        assert _base_forms("taxes") == ("tax",)

    def test_es_is_not_stripped_after_a_consonant(self) -> None:
        """ "offences" must not become "offenc", a string no corpus contains."""
        assert _base_forms("offences") == ("offence",)

    def test_a_y_plural_is_restored(self) -> None:
        assert _base_forms("duties") == ("duty",)

    def test_words_that_merely_end_in_s_are_left_alone(self) -> None:
        for term in ("process", "business", "address", "witness"):
            assert _base_forms(term) == (), term

    def test_short_words_are_left_alone(self) -> None:
        assert _base_forms("was") == ()

    def test_an_irregular_plural_is_simply_not_handled(self) -> None:
        """Deliberate: "children" is common in the corpus in its own right, so
        no variant is needed. This is a spelling check, not a lemmatiser."""
        assert _base_forms("children") == ()
