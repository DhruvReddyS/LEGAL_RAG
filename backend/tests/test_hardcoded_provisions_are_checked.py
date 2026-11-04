"""A duty asserted on a provision number nothing verifies.

The compliance checklist names the provision behind each police duty --
"BNSS s.48(1)" for notifying a relative of an arrest -- and the concept
bridges route a question straight at a section. Both are written into the
source. If an amendment renumbers a section, the checklist keeps telling an
officer the duty arises under a provision that no longer says so, and every
unit test asserting "s.48(1) requires notifying a relative" asserts the stale
number against itself and passes.

These tests cover the extraction half of the guard, which is the half that
runs without the index.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "check_provision_drift", ROOT / "scripts" / "check_provision_drift.py"
)
assert SPEC and SPEC.loader
drift = importlib.util.module_from_spec(SPEC)
sys.modules["check_provision_drift"] = drift
SPEC.loader.exec_module(drift)


def write_module(tmp_path: Path, name: str, body: str) -> Path:
    root = tmp_path / "app"
    root.mkdir(exist_ok=True)
    (root / name).write_text(body, encoding="utf-8")
    return root


def test_the_prose_form_the_compliance_checklist_uses_is_extracted(tmp_path):
    root = write_module(
        tmp_path,
        "compliance.py",
        'RULES = [("notify_relative", "Tell a relative.", "BNSS s.48(1)", "Sub-section (1).")]\n',
    )
    found = drift.extract(root)
    assert [(c.statute, c.section) for c in found] == [("BNSS", "48")], (
        "the section root is what resolves; 48(1) must reduce to 48"
    )
    assert found[0].line == 1
    assert "BNSS s.48(1)" in found[0].text


def test_a_sub_clause_citation_reduces_to_its_section(tmp_path):
    """BNSS s.193(3)(i)(a) is clause (a) of a section. The index records
    sections, so the guard resolves the section and must not go looking for a
    clause it will never find."""
    root = write_module(tmp_path, "m.py", 'X = "BNSS s.193(3)(i)(a)"\n')
    found = drift.extract(root)
    assert [(c.statute, c.section) for c in found] == [("BNSS", "193")]


def test_the_paired_literal_form_the_concept_bridges_use_is_extracted(tmp_path):
    """_Concept("BNSS", "47", ...) routes a question at a provision with no
    citation text at all. A regex looking for "s." misses it entirely, and a
    renumbering there sends the reader somewhere wrong with nothing to notice
    it by."""
    root = write_module(
        tmp_path,
        "bridges.py",
        '_Concept("BNSS", "47", "arrest-right implementation", all_of=(("arrest",),))\n'
        '_Concept("BSA", "1", "evidence-law currency", all_of=(("evidence",),))\n',
    )
    found = drift.extract(root)
    assert sorted((c.statute, c.section) for c in found) == [("BNSS", "47"), ("BSA", "1")]


def test_an_interpolated_citation_is_reported_rather_than_dropped(tmp_path):
    """f"BNSS s.187(3)({'i' if days == 90 else 'ii'})" cannot be resolved from
    source text. Dropping it would quietly shrink the set being checked, so it
    is named in the report."""
    root = write_module(
        tmp_path,
        "m.py",
        "X = f\"BNSS s.187(3)({'i' if days == 90 else 'ii'})\"\n",
    )
    found = drift.extract(root)
    assert [(c.statute, c.section) for c in found] == [("BNSS", "187")]
    assert found[0].interpolated is True
    summary = drift.report_extraction(found)
    assert summary["unresolvable_because_interpolated"], "the interpolated citation vanished"


def test_a_repealed_code_is_not_checked_as_a_live_duty(tmp_path):
    """IPC, CrPC and IEA appear only in the concordance and the repeal
    detector, where naming them is the point. Requiring them to be reachable
    as current law would fail by design."""
    root = write_module(
        tmp_path,
        "m.py",
        'OLD = ["IPC s.302", "CrPC s.154", "IEA s.65B"]\nNEW = ["BNS s.103"]\n',
    )
    found = drift.extract(root)
    assert [(c.statute, c.section) for c in found] == [("BNS", "103")]


def test_modules_that_only_describe_repeal_are_skipped_and_said_to_be(tmp_path):
    """section_mapping.py names new-code sections as mapping targets, not as
    duties. Skipping it is right; skipping it silently is not."""
    root = write_module(tmp_path, "section_mapping.py", 'M = {"IPC 302": "BNS s.103"}\n')
    (root / "duties.py").write_text('D = "BNSS s.35(1)(b)"\n', encoding="utf-8")
    found = drift.extract(root)
    assert [(c.statute, c.section) for c in found] == [("BNSS", "35")]
    assert "section_mapping.py" in drift.report_extraction(found)["descriptive_modules_skipped"]


def test_several_uses_of_one_provision_group_together(tmp_path):
    """s.192(1) is cited five times in the checklist. The report is about
    provisions to verify, not occurrences, and a failure must name where each
    one is used."""
    root = write_module(
        tmp_path,
        "m.py",
        'A = "BNSS s.192(1)"\nB = "BNSS s.192(2)"\nC = "BNSS s.192(1)"\n',
    )
    grouped = drift.by_provision(drift.extract(root))
    assert sorted(grouped) == [("BNSS", "192")]
    assert len(grouped[("BNSS", "192")]) == 3
    assert [c.line for c in grouped[("BNSS", "192")]] == [1, 2, 3]


def test_sections_are_read_from_the_field_and_from_a_heading(tmp_path):
    """`section` is None on documents the chunker could not section, and the
    bare Acts in this corpus are among them -- the section number is in the
    heading path instead. Reading only the field would report every provision
    as unreachable."""
    assert drift._sections_on({"section": "48(1)"}) == {"48"}
    assert drift._sections_on({"heading_path": ["Chapter V", "Section 48. Procedure on arrest"]}) == {"48"}
    assert drift._sections_on({"section": None, "heading_path": ["s. 193 Report"]}) == {"193"}
    assert drift._sections_on({"section": None, "heading_path": ["Document"]}) == set()


def test_the_real_source_still_asserts_duties_on_hardcoded_provisions():
    """The condition this guard exists for. If these citations are ever
    replaced by something resolved from the corpus, the guard is obsolete and
    should be removed rather than left asserting a shape that no longer
    exists."""
    found = drift.extract()
    summary = drift.report_extraction(found)
    assert summary["citations"] >= 60, summary
    modules = summary["modules"]
    assert any("investigation_compliance.py" in m for m in modules), (
        "the checklist that motivated this guard is no longer covered"
    )
    assert any("citation_following.py" in m for m in modules), (
        "the concept bridges are no longer covered"
    )
    assert set(summary["provisions_per_statute"]) <= {"BNSS", "BNS", "BSA"}


def test_sections_in_the_corpus_are_found_through_the_real_authority_check(monkeypatch):
    """This gate could not pass: it handed a whole payload to a check expecting a type."""
    import asyncio
    from types import SimpleNamespace

    point = SimpleNamespace(
        payload={
            "act_name": "THE BHARATIYA NAGARIK SURAKSHA SANHITA, 2023",
            "title": "THE BHARATIYA NAGARIK SURAKSHA SANHITA, 2023",
            "section": "173",
            "document_type": "bare_act",
            "heading_path": [],
        }
    )

    class _Client:
        async def scroll(self, **kwargs):
            return [point], None

        async def close(self):
            return None

    import app.core.qdrant as qdrant

    monkeypatch.setattr(qdrant, "create_qdrant_client", lambda: _Client())
    reachable = asyncio.run(drift.sections_in_corpus("any"))
    assert "173" in reachable["BNSS"]
