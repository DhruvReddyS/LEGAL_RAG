"""The claim budget is a ceiling on ground coverage, so it is asserted.

Ten claims across five categories is about two per category. BNSS s.35(1)
enumerates ten grounds, s.193(3)(i) lists nine clauses, and s.43(3) lists
the offences for which handcuffs are permitted. A cap below those is a
ceiling no amount of retrieval quality can lift -- measured on 6 September,
arrest-current-law named six of ten grounds and missed two that were
retrieved.
"""

from __future__ import annotations

import pytest

from app.agents.reasoning_agent import (
    MAX_CLAIM_CHARACTERS,
    MAX_CLAIMS,
    MAX_EVIDENCE_TEXT_CHARACTERS,
)


# The enumerations a correct answer has to be able to hold, with the count
# the Sanhita actually gives. Taken from the Act, not from what the system
# currently produces.
ENUMERATIONS = {
    "BNSS s.35(1) grounds for arrest without warrant": 10,
    "BNSS s.193(3)(i) contents of the police report": 9,
    "BNSS s.192(1) case diary requirements": 5,
}


def test_which_enumerations_the_budget_can_hold() -> None:
    """Recorded, not asserted away.

    An answer needs about four claims of framing around any list, so an
    enumeration of N needs N+4. The cap was raised to 18 to clear the
    longest and measured: coverage did not move, latency p50 went 53 s to
    154 s, and two questions that previously published fell to a 15-word
    refusal, because a larger budget produces more speculative claims and
    the claim-level support ratio drops under the fabrication floor.

    So this states which lists fit and which do not, and fails when that
    changes in either direction -- shrinking the cap silently, or raising
    it without deleting this record.
    """
    fits = {name for name, items in ENUMERATIONS.items() if items + 4 <= MAX_CLAIMS}
    does_not = set(ENUMERATIONS) - fits

    assert fits == {"BNSS s.192(1) case diary requirements"}
    assert does_not == {
        "BNSS s.35(1) grounds for arrest without warrant",
        "BNSS s.193(3)(i) contents of the police report",
    }, (
        "which enumerations fit the claim budget has changed; if the cap was "
        "raised, measure ground coverage and latency before recording it here"
    )


def test_the_cap_is_not_raised_without_a_latency_measurement() -> None:
    """Output length is the largest single cost in a Deep run.

    Every claim is decoded and then verified, so the cap trades ground
    coverage against latency directly. This is a reminder that the number
    is a trade-off and not a maximum to be pushed.
    """
    assert MAX_CLAIMS <= 12, (
        "18 was measured: latency p50 53 s -> 154 s with no coverage gain. "
        "Raise this only alongside a latency measurement showing otherwise"
    )


def test_a_claim_stays_short_enough_to_verify_individually() -> None:
    """Verification grades each claim against one chunk's premise text.

    A claim longer than the evidence it cites cannot be entailed by it.
    """
    assert MAX_CLAIM_CHARACTERS < MAX_EVIDENCE_TEXT_CHARACTERS


def test_the_prompt_asks_for_enumeration_where_the_evidence_enumerates() -> None:
    """The cap alone does not lift coverage.

    The prompt previously said "prefer fewer, denser claims" without
    qualification, which is right for an argument and wrong for a list of
    statutory grounds. Raising the cap while leaving that instruction in
    place would change nothing.
    """
    import inspect

    from app.agents import reasoning_agent

    body = inspect.getsource(reasoning_agent)
    # The prompt line itself, not the word anywhere in the file. The first
    # version asserted "enumerates" appears in the module, which the
    # explanatory comment above MAX_CLAIMS also satisfies -- so gutting the
    # instruction left the test green.
    instruction = (
        "Where the evidence enumerates -- grounds, conditions, exceptions, "
        "the contents of a document, the\nsteps of a procedure -- give each "
        "item its own short claim"
    )
    assert instruction in body, (
        "the prompt no longer tells the model to enumerate where the provision "
        "does. This instruction stays even though the cap was reverted: it "
        "costs nothing and is the half of the change that was never disproven"
    )
    assert "never the same point restated" in body, (
        "the anti-repetition instruction was dropped; without it a higher cap "
        "buys restatement rather than coverage"
    )
