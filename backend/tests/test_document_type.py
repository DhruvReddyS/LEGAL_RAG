"""Whether a document is the authority, or material about it.

Label B -- "this source concerns a provision that has been repealed, replaced
or renumbered" -- turns on this distinction, and it was inferred at query time
from `source_type`, a field carrying sixteen ad-hoc values that disagree.

The decisive case is the Code of Criminal Procedure, 1898: recorded as a
`law_commission_report`, it is a bare act, and 340 chunks of repealed 1898
statute were competing with the BNSS as if they were operative law.
"""

from __future__ import annotations

import pytest

from app.ingestion.document_type import (
    DocumentType,
    classify_document,
    is_the_authority_itself,
)


class TestTheAuthorityItself:
    @pytest.mark.parametrize(
        ("title", "source_type"),
        [
            ("THE BHARATIYA NAGARIK SURAKSHA SANHITA, 2023", "act"),
            ("THE BHARATIYA NYAYA SANHITA, 2023", "act"),
            ("The Indian Penal Code Act, 1860", "act"),
            ("The Constitution of India (English, as on 1 May 2024)", "constitution"),
        ],
    )
    def test_a_principal_act_is_a_bare_act(self, title, source_type) -> None:
        assert classify_document(title=title, source_type=source_type).document_type is DocumentType.BARE_ACT

    def test_the_1898_code_is_a_bare_act_not_a_commission_report(self) -> None:
        """The misfiling that mattered.

        340 chunks of a repealed 1898 statute were typed as a law commission
        report, so nothing treated them as legislation whose currency matters.
        """
        result = classify_document(
            title="The Code of Criminal Procedure, 1898 1996",
            source_type="law_commission_report",
        )

        assert result.document_type is DocumentType.BARE_ACT
        assert is_the_authority_itself(result.document_type)

    def test_subordinate_legislation_is_still_authority(self) -> None:
        assert is_the_authority_itself(
            classify_document(title="The Arms Rules, 1962", source_type="rule").document_type
        )


class TestMaterialAboutTheAuthority:
    def test_a_law_reform_review_is_commentary_not_the_act(self) -> None:
        """"Review of the Indian Evidence Act" contains the act's name and is
        not the act. Name matching alone gets this wrong."""
        result = classify_document(
            title="Review of the Indian Evidence Act, 1872 2003",
            source_type="law_commission_report",
        )

        assert result.document_type is DocumentType.COMMENTARY
        assert not is_the_authority_itself(result.document_type)

    def test_a_handbook_about_an_act_is_not_the_act(self) -> None:
        result = classify_document(
            title="Handbook on Bharatiya Nyaya Sanhita, 2023 for Police", source_type="handbook"
        )

        assert result.document_type is DocumentType.COMMENTARY

    @pytest.mark.parametrize(
        ("title", "expected"),
        [
            ("Advisory on e-FIR to States 13 May 2022", DocumentType.SOP_OR_CIRCULAR),
            ("SOP for Registration of FIR", DocumentType.SOP_OR_CIRCULAR),
            ("VIHAAN KUMAR vs THE STATE OF HARYANA Crl.A. No. 621/2025", DocumentType.JUDGMENT),
            ("Model Prison Manual 2016", DocumentType.MANUAL),
        ],
    )
    def test_material_about_the_law(self, title, expected) -> None:
        assert classify_document(title=title).document_type is expected


class TestAmendments:
    def test_an_amending_act_is_not_the_principal_act(self) -> None:
        """It is legislation, and it is not the Code. Conflating them would
        make an amendment inherit the principal act's currency."""
        result = classify_document(
            title="The Code of Criminal Procedure (Amendment) Act, 2010", source_type="act"
        )

        assert result.document_type is DocumentType.AMENDMENT
        assert is_the_authority_itself(result.document_type)


class TestOrderingIsTheCorrectness:
    def test_commentary_about_a_principal_act_beats_the_act_rule(self) -> None:
        """Both rules match "Review of the Indian Evidence Act, 1872". The
        specific one has to win, or every commentary becomes an act."""
        assert (
            classify_document(title="Review of the Indian Evidence Act, 1872").document_type
            is DocumentType.COMMENTARY
        )

    def test_an_unmatched_document_is_flagged_rather_than_guessed(self) -> None:
        result = classify_document(title="Download", source_type="official_legal_material")

        assert result.document_type is DocumentType.OTHER
        assert result.ambiguous
        assert "official_legal_material" in result.basis


def test_every_canonical_document_classifies() -> None:
    """The whole corpus, so a rule change cannot silently strand documents."""
    import json
    from collections import Counter
    from pathlib import Path

    manifest = (
        Path(__file__).resolve().parents[2]
        / "data/legal_kb/metadata/canonical_documents.jsonl"
    )
    if not manifest.is_file():
        pytest.skip("corpus manifest is not present in this checkout")

    seen: set[str] = set()
    counts: Counter[str] = Counter()
    ambiguous = 0
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        cid = row.get("canonical_document_id")
        if not cid or cid in seen:
            continue
        seen.add(cid)
        result = classify_document(
            title=row.get("title"),
            act_name=row.get("act_name"),
            source_type=row.get("source_type"),
        )
        counts[str(result.document_type)] += 1
        ambiguous += bool(result.ambiguous)

    assert sum(counts.values()) == len(seen)
    # Judgments and advisories dominate a corpus like this; a classifier that
    # collapsed everything into one bucket would still satisfy the count above.
    assert len(counts) >= 6, f"suspiciously few types: {counts}"
    assert ambiguous <= 10, f"too many unclassifiable documents: {ambiguous}"


class TestLabelBUsesTheStoredType:
    """The point of storing it: Label B stops guessing at query time."""

    def test_a_stored_bare_act_is_the_authority(self) -> None:
        from app.services.repeal_labels import RepealLabel, repeal_notice

        notice = repeal_notice(
            {
                "document_type": "bare_act",
                "act_name": "THE BHARATIYA NAGARIK SURAKSHA SANHITA, 2023",
                "source_type": "advisory",  # deliberately wrong; must be ignored
                "text": "Nothing in section 154 of the Code of Criminal Procedure shall apply.",
            }
        )

        assert notice.label is RepealLabel.NONE, (
            "an in-force act citing a moved provision needs no Label B, and the "
            "stored type must beat a misfiled source_type"
        )

    def test_stored_commentary_gets_label_b(self) -> None:
        from app.services.repeal_labels import RepealLabel, repeal_notice

        notice = repeal_notice(
            {
                "document_type": "commentary",
                "act_name": "Review of the Indian Evidence Act, 1872",
                "source_type": "act",  # deliberately wrong
                "text": "Section 65B of the Indian Evidence Act requires a certificate.",
            }
        )

        assert notice.label is RepealLabel.CONCERNS_REPEALED_PROVISION

    def test_an_index_without_the_field_still_works(self) -> None:
        """The fallback. An older index carries no document_type, and Label B
        must not start mislabelling everything the day the field is added."""
        from app.services.repeal_labels import RepealLabel, repeal_notice

        notice = repeal_notice(
            {
                "source_type": "GOVERNMENT_GUIDANCE",
                "act_name": "Advisory on misuse of section 498A IPC",
                "text": "States shall ensure section 498A IPC is not misused.",
            }
        )

        assert notice.label is RepealLabel.CONCERNS_REPEALED_PROVISION
