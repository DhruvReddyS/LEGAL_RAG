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


@pytest.mark.parametrize(("provision", "items"), sorted(ENUMERATIONS.items()))
def test_the_budget_can_hold_the_longest_enumeration(provision: str, items: int) -> None:
    """Plus room for the answer around it.

    An answer is not only the list: it needs a direct answer, the provision
    it rests on, and its limits. A cap equal to the enumeration would force
    the model to drop either a ground or the framing.
    """
    assert MAX_CLAIMS >= items + 4, (
        f"{provision} has {items} items and the cap is {MAX_CLAIMS}; the answer "
        "cannot list them and still say what it is answering"
    )


def test_the_cap_is_not_raised_without_bound() -> None:
    """Output length is the largest single cost in a Deep run.

    Every claim is decoded and then verified, so the cap trades ground
    coverage against latency directly. This is a reminder that the number
    is a trade-off and not a maximum to be pushed.
    """
    assert MAX_CLAIMS <= 24, (
        "beyond this the decode and verification cost stops being comparable "
        "to the measured 102.6 s p50; raise it only with a latency measurement"
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
        "does; a higher cap on its own changes nothing"
    )
    assert "never the same point restated" in body, (
        "the anti-repetition instruction was dropped; without it a higher cap "
        "buys restatement rather than coverage"
    )
