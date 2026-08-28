from __future__ import annotations

from enum import StrEnum
from typing import Any


class LegalDocumentType(StrEnum):
    CONSTITUTION = "CONSTITUTION"
    ACT = "ACT"
    RULE = "RULE"
    REGULATION = "REGULATION"
    AMENDMENT = "AMENDMENT"
    NOTIFICATION = "NOTIFICATION"
    ORDER = "ORDER"
    CIRCULAR = "CIRCULAR"
    SUPREME_COURT_JUDGMENT = "SUPREME_COURT_JUDGMENT"
    HIGH_COURT_JUDGMENT = "HIGH_COURT_JUDGMENT"
    GOVERNMENT_GUIDANCE = "GOVERNMENT_GUIDANCE"
    POLICE_MANUAL = "POLICE_MANUAL"
    GOVERNMENT_HANDBOOK = "GOVERNMENT_HANDBOOK"
    LAW_COMMISSION_REPORT = "LAW_COMMISSION_REPORT"
    FORM_TEMPLATE = "FORM_TEMPLATE"
    SECONDARY_REFERENCE = "SECONDARY_REFERENCE"


_SOURCE_TYPE_MAP = {
    "constitution": LegalDocumentType.CONSTITUTION,
    "act": LegalDocumentType.ACT,
    "rule": LegalDocumentType.RULE,
    "regulation": LegalDocumentType.REGULATION,
    "amendment_act": LegalDocumentType.AMENDMENT,
    "notification": LegalDocumentType.NOTIFICATION,
    "order": LegalDocumentType.ORDER,
    "circular": LegalDocumentType.CIRCULAR,
    "law_commission_report": LegalDocumentType.LAW_COMMISSION_REPORT,
    "handbook": LegalDocumentType.GOVERNMENT_HANDBOOK,
    "manual": LegalDocumentType.POLICE_MANUAL,
    "training_module": LegalDocumentType.POLICE_MANUAL,
}


def classify_document(metadata: dict[str, Any], sample_text: str = "") -> LegalDocumentType:
    """Classify using trusted manifest fields first and text only as fallback."""
    source_type = str(metadata.get("source_type") or "").strip().lower()
    category = str(metadata.get("category") or "").strip().lower()
    court = str(metadata.get("court") or "").strip().lower()
    title = str(metadata.get("title") or "").strip().lower()

    if source_type == "judgment":
        if "supreme court" in court or "supreme court" in category:
            return LegalDocumentType.SUPREME_COURT_JUDGMENT
        return LegalDocumentType.HIGH_COURT_JUDGMENT
    if source_type in _SOURCE_TYPE_MAP:
        return _SOURCE_TYPE_MAP[source_type]
    if category.startswith("legal_forms_templates"):
        return LegalDocumentType.FORM_TEMPLATE
    if category.startswith("secondary_open_reference"):
        return LegalDocumentType.SECONDARY_REFERENCE
    if "police" in category or "bprd" in category or "police" in title:
        return LegalDocumentType.POLICE_MANUAL
    if category.startswith("government_handbooks"):
        return LegalDocumentType.GOVERNMENT_HANDBOOK
    if category.startswith("official_guidance"):
        return LegalDocumentType.GOVERNMENT_GUIDANCE

    inferred = f"{title}\n{sample_text[:4000]}".lower()
    if "regulation" in inferred:
        return LegalDocumentType.REGULATION
    if "circular" in inferred:
        return LegalDocumentType.CIRCULAR
    if "form no." in inferred or "application form" in inferred:
        return LegalDocumentType.FORM_TEMPLATE
    return LegalDocumentType.GOVERNMENT_GUIDANCE
