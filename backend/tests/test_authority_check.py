"""What a draft cites, checked against the codes now in force.

The failure this guards against is a petition filed with 2019 citations. It
is not exotic: most CrPC and IPC provisions were renumbered on 1 July 2024,
a quarter of the pairs changed substantively, and a handful were dropped
entirely -- and none of that is visible in the draft.
"""

from __future__ import annotations

import pytest

from app.services.authority_check import AuthorityFinding, check_authorities


def _by_citation(draft: str) -> dict[str, object]:
    return {check.citation: check for check in check_authorities(draft)}


class TestARenumberedProvisionIsNamed:
    def test_anticipatory_bail_moves_from_crpc_438_to_bnss_482(self) -> None:
        found = _by_citation("The applicant relies on section 438 of the Code of Criminal Procedure.")

        check = found["CrPC s.438"]
        assert check.finding in {
            AuthorityFinding.RENUMBERED,
            AuthorityFinding.ELEMENTS_CHANGED,
        }
        assert "BNSS s.482" in check.successors
        assert check.needs_attention

    def test_the_successor_is_stated_not_merely_flagged(self) -> None:
        """A warning that a citation is stale, without the replacement, sends
        the drafter to look it up -- which is the work this is for."""
        check = _by_citation("section 302 IPC")["IPC s.302"]

        assert check.successors
        assert "BNS s.103" in check.advice


class TestAProvisionThatWasNotReEnacted:
    def test_sedition_is_not_offered_a_successor(self) -> None:
        """The finding that cannot be fixed by substituting a number.

        A drafter told "IPC s.124A is now BNS s.152" would file a petition
        about a different offence with different elements. The official
        table records s.124A as deleted, and this must say so.
        """
        check = _by_citation("section 124A of the Indian Penal Code")["IPC s.124A"]

        assert check.finding is AuthorityFinding.NOT_RE_ENACTED
        assert check.successors == ()
        assert "no renumbered equivalent" in check.advice
        assert check.needs_attention

    def test_it_is_distinct_from_an_unknown_provision(self) -> None:
        """"Repealed without replacement" and "not in the table" are
        different answers, and only the first is a finding."""
        checks = _by_citation(
            "section 124A of the Indian Penal Code and section 874 of the Indian Penal Code"
        )

        assert checks["IPC s.124A"].finding is AuthorityFinding.NOT_RE_ENACTED
        assert checks["IPC s.874"].finding is AuthorityFinding.NO_MAPPING_KNOWN


class TestSubstantiveChangeIsSeparatedFromRenumbering:
    def test_a_changed_provision_says_so(self) -> None:
        """s.65B of the Evidence Act is the case advocates ask about.

        Treating BSA s.63 as "s.65B renumbered" gets the certificate
        requirement wrong, and the official table marks the pair changed.
        """
        check = _by_citation("section 65B of the Indian Evidence Act")["IEA s.65B"]

        assert check.finding is AuthorityFinding.ELEMENTS_CHANGED
        assert "check the elements" in check.advice

    def test_not_every_pair_is_marked_changed(self) -> None:
        """A warning on everything is a warning on nothing.

        The flag comes from the source table's own (Change) marker, which
        applies to about a quarter of pairs. If this ever returns changed
        for every citation, the marker has stopped being read.
        """
        draft = " ".join(f"section {n} of the Indian Penal Code" for n in range(300, 420))
        findings = {c.finding for c in check_authorities(draft, max_citations=200)}

        assert AuthorityFinding.ELEMENTS_CHANGED in findings
        # Specifically RENUMBERED, not merely "some other finding". The first
        # version accepted NOT_RE_ENACTED here, which appears from a separate
        # branch, so flagging every mapped pair as changed still passed.
        assert AuthorityFinding.RENUMBERED in findings, (
            "no provision came back as a plain renumbering; the (Change) "
            "marker is not being read and every pair is flagged"
        )


class TestWhatIsNotFlagged:
    def test_a_provision_of_a_code_in_force_is_left_alone(self) -> None:
        check = _by_citation(
            "section 35 of the Bharatiya Nagarik Suraksha Sanhita"
        )["BNSS s.35"]

        assert check.finding is AuthorityFinding.STILL_CURRENT
        assert not check.needs_attention

    @pytest.mark.parametrize(
        ("draft", "expected_code"),
        [
            ("Article 21 of the Constitution", "Constitution"),
            ("section 4 of the Protection of Children from Sexual Offences Act", "POCSO"),
            ("section 138 of the Negotiable Instruments Act", "Negotiable Instruments Act"),
        ],
    )
    def test_a_citation_outside_the_concordance_is_listed_as_unchecked(
        self, draft: str, expected_code: str
    ) -> None:
        """Silently omitting it was the original bug.

        The extractor recognises sixteen acts; the concordance covers six. A
        petition citing POCSO s.4 produced no row at all, which a drafter
        reads as "checked and fine". It is now listed by name, marked
        unchecked, and deliberately not counted as needing attention --
        folding it in would bury the four findings that do.

        The first version of this test looped over the results and asserted
        inside an `if`, so when the citation was dropped the loop body never
        ran and it passed.
        """
        checks = check_authorities(draft)

        assert len(checks) == 1, f"{draft!r} produced {len(checks)} rows, expected 1"
        assert checks[0].code == expected_code
        assert checks[0].finding is AuthorityFinding.NOT_CHECKED
        assert not checks[0].needs_attention
        assert "has not been verified" in checks[0].advice


class TestDraftHandling:
    def test_a_provision_cited_eight_times_is_one_finding(self) -> None:
        """A long petition would otherwise drown its own warnings.

        The extractor already collapses repeats, so this asserts the
        end-to-end property rather than any one layer -- the guard in
        check_authorities is a second line of defence against that changing,
        and a mutation removing it correctly does not fail this test.
        """
        draft = " ".join(["section 438 of the Code of Criminal Procedure"] * 8)

        assert len(check_authorities(draft)) == 1

    def test_the_same_provision_written_two_ways_is_one_finding(self) -> None:
        """"s. 438 CrPC" and the spelled-out form are the same provision."""
        checks = check_authorities(
            "Relying on s. 438 CrPC and on section 438 of the Code of Criminal Procedure."
        )

        assert [c.citation for c in checks] == ["CrPC s.438"]

    def test_order_follows_the_draft(self) -> None:
        checks = check_authorities(
            "First section 302 IPC, then section 438 of the Code of Criminal Procedure."
        )

        assert [c.citation for c in checks] == ["IPC s.302", "CrPC s.438"]

    def test_an_empty_draft_yields_nothing_rather_than_raising(self) -> None:
        assert check_authorities("") == []
        assert check_authorities("   ") == []

    def test_prose_with_no_citations_yields_nothing(self) -> None:
        assert check_authorities("The client denies the allegation entirely.") == []
