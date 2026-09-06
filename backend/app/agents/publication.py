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

from app.schemas.agents import VerificationResult

__all__ = ["PublicationDecision", "publication_decision", "MINIMUM_SUPPORT_RATIO"]

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

    if result.score < MINIMUM_SUPPORT_RATIO:
        return PublicationDecision(
            False,
            f"only {result.score:.0%} of claims were supported, which indicates "
            "fabrication rather than a partial answer",
            len(verified),
        )

    return PublicationDecision(
        True, f"{len(verified)} verified claims", len(verified)
    )
