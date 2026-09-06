"""Whether a verified result is worth publishing.

One definition, used by the node that publishes and by the node that
decides whether to retry, so the graph cannot retry a result it would have
published or publish one it just decided was too weak.

Replaces a gate that read `verification.score < 0.5` and abstained. That
score is a *ratio* -- verified claims over all claims attempted -- and the
gate on it punished thoroughness. A broad question generates more claims,
more of them get rejected, the ratio falls, and the answer is discarded
even though the absolute quantity of verified law is higher than a narrow
question's.

Measured on 6 September 2026, 61 questions: six of the nine wrongly
refused questions had verified claims that never reached the reader.
`child-needing-care` produced **ten** claims that passed verification, ran
for 332 seconds, and printed "insufficient evidence".

This is not a relaxation of verification. Verification judged each claim
against its own chunk and ten passed; only `yes` claims are ever published,
and that is unchanged. What changed is that the presence of rejected
siblings no longer suppresses the survivors -- they were never evidence
against each other.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.agents import ClaimVerification, VerificationResult

__all__ = [
    "PublicationDecision",
    "publication_decision",
    "evidence_addresses_the_question",
    "MINIMUM_SUPPORT_RATIO",
]

# Below this, the model was largely fabricating and even the claims that
# passed deserve suspicion. Deliberately far below the old 0.5: this is a
# fabrication guard, not a quality bar. Quality is carried by per-section
# confidence, which grades what each part of the answer rests on.
MINIMUM_SUPPORT_RATIO = 0.2

# A claim that only qualifies an answer is not an answer. Publishing a
# response made entirely of caveats would be worse than abstaining, because
# it reads as an answer.
_QUALIFYING_ONLY = {"limit"}


@dataclass(frozen=True)
class PublicationDecision:
    publish: bool
    reason: str
    verified_claims: int

    def __bool__(self) -> bool:
        return self.publish


def _claim_level_support(result: VerificationResult) -> float:
    """What fraction of the *claims* the model made were supported.

    `VerificationResult.score` is computed over claim-marker pairs, one per
    citation, so a claim citing three sources contributes three entries. A
    well-sourced claim that one source strongly entails and two merely touch
    scores 1 yes and 2 no, and drags its own ratio down -- the metric
    penalises exactly the sourcing it should reward.

    Measured 6 September: art19-free-speech had four claims pass
    verification and still abstained, because the pair ratio fell under the
    fabrication floor.

    A claim is supported when *any* of its cited sources entails it, which
    is the same standard publication already applies: those claims are
    published, so they must count as supported when deciding whether to
    publish at all.
    """
    if not result.claims:
        return 0.0
    by_claim: dict[str, bool] = {}
    for item in result.claims:
        by_claim[item.claim] = by_claim.get(item.claim, False) or item.verdict == "yes"
    return sum(by_claim.values()) / len(by_claim)


def publication_decision(result: VerificationResult | None) -> PublicationDecision:
    if result is None:
        return PublicationDecision(False, "no verification result", 0)

    verified = [claim for claim in result.claims if claim.verdict == "yes"]
    if not verified:
        return PublicationDecision(
            False, "no claim survived verification", 0
        )

    if all(claim.category in _QUALIFYING_ONLY for claim in verified):
        return PublicationDecision(
            False,
            "every surviving claim is a caveat; none of them answers the question",
            len(verified),
        )

    support = _claim_level_support(result)
    if support < MINIMUM_SUPPORT_RATIO:
        return PublicationDecision(
            False,
            f"only {support:.0%} of claims were supported, which indicates "
            "fabrication rather than a partial answer",
            len(verified),
        )

    return PublicationDecision(
        True, f"{len(verified)} verified claims", len(verified)
    )


def evidence_addresses_the_question(
    query: str,
    hits: list,
    distinctive_terms: set[str],
) -> bool:
    """Whether any retrieved passage is about what was asked.

    Verification asks whether a claim follows from its source. Nothing asked
    whether the source addresses the question, so a corpus gap with adjacent
    material produced a grounded answer to a question it could not support:
    noise-pollution was answered from passages containing neither "noise" nor
    "neighbouring".

    The Fast lane has solved this since it was written. This calls that
    lane's own `publishable_hits` rather than reimplementing the rule --
    the Deep and Fast paths have drifted apart before, and a second copy of
    a relevance floor is how it happens.

    Measured against live retrieval on 18 golden questions before shipping:
    it refuses noise-pollution, which is currently answered wrongly, and
    changes nothing else. It does **not** catch workplace-harassment, where
    the corpus holds the POSH committee-constitution advisory but not the
    complaint pathway: five of eight passages carry "harassment" and
    "workplace" honestly. Right topic, wrong sub-topic is not a lexical
    problem and this does not pretend to solve it.
    """
    # Imported here: fast_research pulls in the retrieval stack, and the
    # publication rules are otherwise free of it.
    from app.services.fast_research import _focus_tokens, publishable_hits

    if not hits:
        return False
    # A query with no focus terms is refused one layer down: _lexical_coverage
    # returns 0.0 for an empty term set rather than 1.0, deliberately, so that
    # "is it?" cannot be answered by whichever passage the vector search
    # happened to return. Re-checking it here read as defence in depth and was
    # dead code -- no mutation of it could fail a test, because the behaviour
    # is enforced and tested in fast_research.
    focus = _focus_tokens(query)
    return bool(
        publishable_hits(
            hits,
            query=query,
            focus_tokens=focus,
            distinctive_terms=distinctive_terms,
        )
    )
