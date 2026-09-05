"""What kind of document this is: the authority itself, or material about it.

Label B -- "this source concerns a provision that has been repealed, replaced
or renumbered" -- turns on exactly that distinction, and it was being inferred
at query time from `source_type`, a field with sixteen ad-hoc values that
disagree with each other. `law_commission_report` currently holds both a
genuine commentary and the Code of Criminal Procedure, 1898, which is a bare
act; the second is why 389 pages of a repealed 1898 statute compete with the
BNSS as operative law.

Deterministic: a table of rules over the curated title, act name and existing
source type. No model, and no inference at query time -- the answer is decided
once, at ingestion, and stored.

The rules are ordered most specific first. An amendment act is an act, and a
handbook about an act is not the act, so the order is the whole of the
correctness here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class DocumentType(StrEnum):
    BARE_ACT = "bare_act"
    AMENDMENT = "amendment"
    COMMENTARY = "commentary"
    JUDGMENT = "judgment"
    SOP_OR_CIRCULAR = "sop_or_circular"
    MANUAL = "manual"
    RULES_OR_REGULATIONS = "rules_or_regulations"
    OTHER = "other"


# Types that ARE the authority. Label B applies to everything else: material
# about the law remains operative even when the provision it discusses moved.
AUTHORITY_TYPES = frozenset(
    {DocumentType.BARE_ACT, DocumentType.AMENDMENT, DocumentType.RULES_OR_REGULATIONS}
)


@dataclass(frozen=True)
class Classification:
    document_type: DocumentType
    basis: str
    ambiguous: bool = False


_TITLE_RULES: tuple[tuple[re.Pattern[str], DocumentType, str], ...] = (
    # Commentary first: "Review of the Indian Evidence Act" is about an act.
    (re.compile(r"\breview of\b|\bworking paper\b|\bconsultation paper\b", re.I),
     DocumentType.COMMENTARY, "law-reform review"),
    (re.compile(r"\bhandbook\b|\bcompendium\b|\bcommentary\b|\bstudy\b|\bprimer\b", re.I),
     DocumentType.COMMENTARY, "handbook or compendium"),
    (re.compile(r"\btraining (?:manual|module)\b|\bcourse\b", re.I),
     DocumentType.MANUAL, "training material"),
    (re.compile(r"\bmodel (?:prison )?manual\b|\bmanual\b", re.I),
     DocumentType.MANUAL, "manual"),
    # An amendment act is still legislation, but not the principal act.
    (re.compile(r"\(amendment\)\s*act\b|\bamendment act\b|\bamendments? in\b", re.I),
     DocumentType.AMENDMENT, "amending instrument"),
    (re.compile(r"\brules?,?\s*\d{4}\b|\bregulations?,?\s*\d{4}\b|\bg\.s\.r\.|\bs\.o\.\s*\d", re.I),
     DocumentType.RULES_OR_REGULATIONS, "subordinate legislation"),
    (re.compile(r"\badvisory\b|\bcircular\b|\bsop\b|\bstandard operating\b|\bguidelines?\b", re.I),
     DocumentType.SOP_OR_CIRCULAR, "advisory or SOP"),
    (re.compile(r"\bvs\b|\bv\.\s|\bw\.p\.|\bcrl\.a\.|\bcivil appeal\b|\bcriminal appeal\b"
                r"|\bs\.l\.p\.|\bsmc\b", re.I),
     DocumentType.JUDGMENT, "case citation in the title"),
    (re.compile(r"\bconstitution of india\b", re.I),
     DocumentType.BARE_ACT, "the Constitution"),
    (re.compile(r"\b(?:act|sanhita|adhiniyam|code|sahita),?\s*\d{4}\b", re.I),
     DocumentType.BARE_ACT, "principal legislation"),
)

# Where the title says nothing, fall back to the curated source_type.
_SOURCE_TYPE_MAP: dict[str, tuple[DocumentType, str]] = {
    "judgment": (DocumentType.JUDGMENT, "source_type"),
    "constitution": (DocumentType.BARE_ACT, "source_type"),
    "act": (DocumentType.BARE_ACT, "source_type"),
    "amendment_act": (DocumentType.AMENDMENT, "source_type"),
    "rule": (DocumentType.RULES_OR_REGULATIONS, "source_type"),
    "notification": (DocumentType.RULES_OR_REGULATIONS, "source_type"),
    "law_commission_report": (DocumentType.COMMENTARY, "source_type"),
    "advisory": (DocumentType.SOP_OR_CIRCULAR, "source_type"),
    "official_guidance": (DocumentType.SOP_OR_CIRCULAR, "source_type"),
    "guidance": (DocumentType.SOP_OR_CIRCULAR, "source_type"),
    "sop": (DocumentType.SOP_OR_CIRCULAR, "source_type"),
    "order": (DocumentType.SOP_OR_CIRCULAR, "source_type"),
    "manual": (DocumentType.MANUAL, "source_type"),
    "handbook": (DocumentType.COMMENTARY, "source_type"),
    "training_module": (DocumentType.MANUAL, "source_type"),
}

# A bare act misfiled as something else. The Code of Criminal Procedure, 1898
# is recorded as a law_commission_report and carries 340 chunks of repealed
# statute that then compete with the BNSS as if they were operative law.
_KNOWN_BARE_ACTS = re.compile(
    r"^(?:the\s+)?(?:code of criminal procedure|indian penal code|indian evidence act"
    r"|bharatiya (?:nyaya sanhita|nagarik suraksha sanhita|sakshya adhiniyam)"
    r"|constitution of india)",
    re.I,
)


def classify_document(
    *, title: str | None = None, act_name: str | None = None, source_type: str | None = None
) -> Classification:
    """The document's kind, decided once and stored."""
    name = f"{(act_name or '').strip()} {(title or '').strip()}".strip()

    # A principal act whose name is unmistakable wins over a misfiled type,
    # but not over an amendment or a commentary about it.
    if _KNOWN_BARE_ACTS.match((act_name or title or "").strip()):
        for pattern, kind, basis in _TITLE_RULES:
            if kind in {DocumentType.AMENDMENT, DocumentType.COMMENTARY} and pattern.search(name):
                return Classification(kind, f"{basis} (about a principal act)")
        return Classification(DocumentType.BARE_ACT, "named principal act")

    for pattern, kind, basis in _TITLE_RULES:
        if pattern.search(name):
            return Classification(kind, basis)

    mapped = _SOURCE_TYPE_MAP.get((source_type or "").strip().lower())
    if mapped is not None:
        return Classification(mapped[0], mapped[1])

    return Classification(
        DocumentType.OTHER,
        f"no rule matched (source_type={source_type!r})",
        ambiguous=True,
    )


def is_the_authority_itself(document_type: str | DocumentType) -> bool:
    """Whether Label A applies rather than Label B."""
    try:
        return DocumentType(str(document_type)) in AUTHORITY_TYPES
    except ValueError:
        return False
