"""Nothing may read the raw currency fields to make a decision.

Seven instances of one bug were found one at a time, each reading as
protective while doing nothing:

  1. the admin owner filter, skipped when the case list was empty
  2. an unscoped private-corpus query, allowed because case_ids was empty
  3. `is_superseded is True`, on a field nothing wrote
  4. the same field filtered `== False`, where None is neither
  5. a 0.15 threshold compared against a 0.016 RRF score
  6. `is_current is not True` in the Deep answer, giving the mildest message
     on the source needing the strongest
  7. the same expression in the Fast lane, firing its currency notice on every
     answer, and the same again in document analysis, which could never return
     "superseded" at all

The shape is always the same: a check whose input is effectively never set.
`resolve_currency` exists so the decision is taken in one place from data that
is actually populated. This test stops anyone going back to the field.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]

# Fields that are nullable in the payload and effectively never true in this
# corpus. Reading them directly to decide anything reproduces the bug.
GUARDED_FIELDS = {"is_current", "is_superseded"}

# The resolver itself must read them -- that is its job -- and ingestion writes
# them.
ALLOWED = {
    "app/services/currency.py",
    "app/ingestion/qdrant_writer.py",
    "app/ingestion/chunker.py",
    "app/ingestion/metadata.py",
    "app/ingestion/repair_metadata.py",
    "app/ingestion/validate.py",
}


def _reads(path: Path) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        left = node.left
        field = None
        if (
            isinstance(left, ast.Call)
            and isinstance(left.func, ast.Attribute)
            and left.func.attr == "get"
            and left.args
            and isinstance(left.args[0], ast.Constant)
        ):
            field = left.args[0].value
        elif isinstance(left, ast.Subscript) and isinstance(left.slice, ast.Constant):
            field = left.slice.value
        if field in GUARDED_FIELDS:
            found.append((node.lineno, str(field)))
    return found


def test_no_module_decides_currency_from_the_raw_field() -> None:
    offenders: list[str] = []
    for path in sorted((BACKEND / "app").rglob("*.py")):
        if "__pycache__" in str(path):
            continue
        relative = str(path.relative_to(BACKEND))
        if relative in ALLOWED:
            continue
        for line, field in _reads(path):
            offenders.append(f"{relative}:{line} reads {field!r}")

    assert not offenders, (
        "these decide currency from a field that is effectively never set; use "
        f"resolve_currency instead: {offenders}"
    )


def test_the_sweep_would_notice_a_regression() -> None:
    """The detector, checked against a known instance.

    A test that scans for a pattern is worthless if the scan is broken, and a
    passing empty scan looks identical to a clean codebase.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        offending = Path(tmp) / "bad.py"
        offending.write_text(
            "def f(payload):\n"
            "    if payload.get('is_current') is not True:\n"
            "        return 'unverified'\n",
            encoding="utf-8",
        )
        assert _reads(offending) == [(2, "is_current")]


@pytest.mark.parametrize(
    ("module", "symbol"),
    [
        ("app.services.fast_research", "resolve_currency"),
        ("app.services.document_analysis", "resolve_currency"),
        ("app.agents.response_generation", "resolve_currency"),
    ],
)
def test_the_lanes_import_the_resolver(module: str, symbol: str) -> None:
    """Each place that used to read the field now resolves instead."""
    import importlib

    assert hasattr(importlib.import_module(module), symbol)


class TestTheFastLaneCurrencyNotice:
    """The seventh instance, and the one the sweep found with no test at all.

    `any(hit.payload.get("is_current") is not True for hit in hits)` is true
    for every hit in this corpus, so the notice appeared on every Fast answer
    and could not distinguish a repealed Act from a circular nobody has
    checked. A warning that always fires carries no information.
    """

    def test_a_superseded_source_is_named(self) -> None:
        from app.services.fast_research import currency_notice

        notice = currency_notice(
            [{"act_name": "The Code of Criminal Procedure, 1973 (Act No.2 of 1974)"}]
        )

        assert notice is not None
        assert "no longer in force" in notice
        assert "Code of Criminal Procedure" in notice

    def test_an_unverified_source_gets_the_milder_notice(self) -> None:
        from app.services.fast_research import currency_notice

        notice = currency_notice([{"act_name": "Advisory on e-FIR to States"}])

        assert notice is not None
        assert "not verified" in notice
        assert "no longer in force" not in notice

    def test_an_all_in_force_answer_gets_no_notice_at_all(self) -> None:
        """The property that makes the notice worth reading, and the one the
        old expression could never produce."""
        from app.services.fast_research import currency_notice

        assert (
            currency_notice(
                [
                    {"act_name": "THE BHARATIYA NAGARIK SURAKSHA SANHITA, 2023"},
                    {"act_name": "THE BHARATIYA NYAYA SANHITA, 2023"},
                ]
            )
            is None
        )

    def test_a_superseded_source_outranks_an_unverified_one(self) -> None:
        """Mixed evidence must surface the stronger warning."""
        from app.services.fast_research import currency_notice

        notice = currency_notice(
            [
                {"act_name": "Advisory on e-FIR to States"},
                {"act_name": "The Indian Penal Code Act, 1860"},
            ]
        )

        assert notice is not None and "no longer in force" in notice

    def test_it_no_longer_reads_the_field_directly(self) -> None:
        import inspect

        from app.services import fast_research

        assert 'get("is_current") is not True' not in inspect.getsource(fast_research)
