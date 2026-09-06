"""How well each part of an answer is actually grounded.

One confidence number for a whole answer hides the thing a reader needs.
An answer can state the governing provision from the Sanhita itself and
then list practical next steps drawn from a single circular; those two
parts do not deserve the same trust, and a single 0.86 tells the reader
nothing about which is which.

Every input here is already on the chunk payload -- document type, currency
status, source identity -- so this is a table lookup over the published
claims, not a judgement. Nothing calls a model.

The rules fail closed in three specific ways, each because the alternative
flatters an answer that should not be trusted:

* A section grounded in one source is never strong, however good that
  source is. One passage read one way is how a confident wrong answer gets
  made.
* A section with no primary authority is never strong. Three circulars
  agreeing with each other still do not establish a legal position; they
  establish what an administrator believed it to be.
* A section citing anything whose currency is unverified is never strong.
  "Probably still in force" is not a foundation, and the whole currency
  design exists so that this stays visible rather than being averaged away.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Iterable, Mapping

from app.services.currency import CurrencyStatus, resolve_currency

__all__ = [
    "AuthorityTier",
    "SectionConfidence",
    "ConfidenceLabel",
    "authority_tier",
    "section_confidence",
]


class ConfidenceLabel(StrEnum):
    STRONG = "strong"
    MODERATE = "moderate"
    LIMITED = "limited"


class AuthorityTier(StrEnum):
    """What kind of thing the source is, for the purpose of grounding a claim."""

    PRIMARY = "primary"          # the Act, its amendments, rules made under it
    DECISION = "decision"        # a court construing it
    GUIDANCE = "guidance"        # a circular, SOP or manual: how officials read it
    SECONDARY = "secondary"      # commentary, or unknown


_TIER_BY_DOCUMENT_TYPE = {
    "bare_act": AuthorityTier.PRIMARY,
    "amendment": AuthorityTier.PRIMARY,
    "rules_or_regulations": AuthorityTier.PRIMARY,
    "judgment": AuthorityTier.DECISION,
    "sop_or_circular": AuthorityTier.GUIDANCE,
    "manual": AuthorityTier.GUIDANCE,
    "commentary": AuthorityTier.SECONDARY,
    "other": AuthorityTier.SECONDARY,
}

# Either of these can establish a legal position. Guidance cannot: it is
# evidence of practice, not of law.
_ESTABLISHING = {AuthorityTier.PRIMARY, AuthorityTier.DECISION}


def authority_tier(payload: Mapping[str, Any]) -> AuthorityTier:
    """The tier of one source.

    Reads the stored document_type, decided once at ingestion, and falls
    back to source_type only when the newer field is absent -- an index
    built before the classifier existed must not silently score every
    passage as secondary.
    """
    stored = str(payload.get("document_type") or "").strip().lower()
    if stored in _TIER_BY_DOCUMENT_TYPE:
        return _TIER_BY_DOCUMENT_TYPE[stored]
    legacy = str(payload.get("source_type") or "").strip().lower()
    if legacy in {"act", "rule", "notification"}:
        return AuthorityTier.PRIMARY
    if legacy == "judgment":
        return AuthorityTier.DECISION
    if legacy in {"advisory", "guidance", "official_guidance", "sop", "manual", "order"}:
        return AuthorityTier.GUIDANCE
    return AuthorityTier.SECONDARY


@dataclass(frozen=True)
class SectionConfidence:
    """Why a section is trusted as much as it is, not merely how much."""

    section: str
    claim_count: int
    source_count: int
    tiers: tuple[AuthorityTier, ...]
    currency_unverified: bool
    label: ConfidenceLabel
    reason: str

    def as_row(self) -> dict[str, Any]:
        return {
            "section": self.section,
            "claims": self.claim_count,
            "sources": self.source_count,
            "authority": sorted({str(t) for t in self.tiers}),
            "currency_unverified": self.currency_unverified,
            "confidence": str(self.label),
            "reason": self.reason,
        }


def section_confidence(
    section: str,
    chunk_ids: Iterable[str],
    payload_by_chunk_id: Mapping[str, Mapping[str, Any]],
    *,
    claim_count: int,
) -> SectionConfidence:
    """Grade one section from the sources its published claims cite."""
    ids = [chunk_id for chunk_id in dict.fromkeys(chunk_ids)]
    payloads = [payload_by_chunk_id[i] for i in ids if i in payload_by_chunk_id]

    tiers = tuple(authority_tier(payload) for payload in payloads)
    unverified = any(
        resolve_currency(payload).status is CurrencyStatus.UNVERIFIED
        for payload in payloads
    )
    establishing = [tier for tier in tiers if tier in _ESTABLISHING]

    # Ordered from the most disqualifying, so the reason names the first
    # thing that actually caps this section rather than the last.
    if not payloads:
        label, reason = ConfidenceLabel.LIMITED, "no source could be resolved for this section"
    elif not establishing:
        label, reason = (
            ConfidenceLabel.LIMITED,
            "grounded only in guidance or commentary, which shows how officials "
            "read the law rather than what it says",
        )
    elif len(payloads) == 1:
        label, reason = (
            ConfidenceLabel.MODERATE,
            "grounded in a single source; a second would be needed to corroborate it",
        )
    elif unverified:
        label, reason = (
            ConfidenceLabel.MODERATE,
            "one or more cited sources has an unverified current-law status",
        )
    else:
        label, reason = (
            ConfidenceLabel.STRONG,
            f"grounded in {len(payloads)} sources including primary authority, "
            "all of verified current status",
        )

    return SectionConfidence(
        section=section,
        claim_count=claim_count,
        source_count=len(payloads),
        tiers=tiers,
        currency_unverified=unverified,
        label=label,
        reason=reason,
    )
