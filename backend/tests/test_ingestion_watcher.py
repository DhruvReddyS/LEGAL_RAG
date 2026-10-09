"""The watcher must not lie about progress or the time left.

It is the only thing reporting on a build that runs for a day, so a wrong
milestone or a wrong ETA is worse than no watcher: someone plans around it.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "watch_ingestion", ROOT / "scripts" / "watch_ingestion.py"
)
assert SPEC and SPEC.loader
watch = importlib.util.module_from_spec(SPEC)
sys.modules["watch_ingestion"] = watch
SPEC.loader.exec_module(watch)


def test_a_watcher_started_mid_build_reports_the_next_milestone_not_the_last():
    """Starting at 55% must report 60% next. Re-announcing 50% -- passed hours
    ago -- would read as progress that just happened."""
    assert watch.next_milestone(55.2, 10) == 60
    assert watch.next_milestone(0.0, 10) == 10
    assert watch.next_milestone(99.9, 10) == 100
    assert watch.next_milestone(12.0, 5) == 15


def test_milestones_advance_without_repeating_or_skipping():
    """A build can cross two milestones between polls on a fast run; each is
    reported once and none is lost."""
    step, mark, seen = 10, watch.next_milestone(55.2, 10), []
    for percent in (56, 61, 62, 83, 100):
        while percent >= mark:
            seen.append(mark)
            mark += step
    assert seen == [60, 70, 80, 90, 100]


def test_the_rate_counts_only_work_inside_the_window(tmp_path, monkeypatch):
    """The ETA uses a trailing window because a cumulative rate averages in
    whatever was slow at the start -- for v5 an evicted model and a CPU latch,
    neither of which still applies -- and reads pessimistically for hours."""
    now = datetime.now(timezone.utc)
    completed = {
        "recent-a": {"completed_at": (now - timedelta(minutes=30)).isoformat()},
        "recent-b": {"completed_at": (now - timedelta(minutes=90)).isoformat()},
        "old": {"completed_at": (now - timedelta(hours=20)).isoformat()},
    }
    pages = {"recent-a": 100, "recent-b": 200, "old": 9_000}

    rate = watch.rate_over_window(completed, pages, hours=3.0)
    assert rate == (100 + 200) / 3.0, "work outside the window changed the rate"


def test_a_malformed_timestamp_does_not_stop_the_watcher(tmp_path):
    """The ledger is rewritten after every document. A row read mid-write must
    be skipped, not crash the only thing reporting on the build."""
    now = datetime.now(timezone.utc)
    completed = {
        "good": {"completed_at": (now - timedelta(minutes=10)).isoformat()},
        "truncated": {"completed_at": "2026-10-09T12:1"},
        "absent": {},
    }
    rate = watch.rate_over_window(completed, {"good": 60, "truncated": 10, "absent": 10}, 1.0)
    assert rate == 60


def test_a_ledger_caught_mid_write_is_retried_not_read_as_zero(tmp_path, monkeypatch):
    """Reporting zero progress because a read landed mid-write would look like
    the build had restarted from nothing."""
    logs = tmp_path / "logs"
    logs.mkdir()
    path = logs / "ingestion_checkpoint.test_collection.json"
    path.write_text("{ this is not json yet", encoding="utf-8")
    monkeypatch.setattr(watch, "LOGS", logs)
    monkeypatch.setattr(watch.time, "sleep", lambda _: None)

    completed, failed = watch.read_ledger("test_collection")
    assert completed == {} and failed == {}, "a partial read must not invent progress"

    path.write_text(json.dumps({"completed": {"a": {}}, "failed": {}}), encoding="utf-8")
    completed, failed = watch.read_ledger("test_collection")
    assert list(completed) == ["a"]


def test_an_eta_that_cannot_be_computed_says_so_rather_than_printing_a_number():
    """Before any document finishes the rate is zero. '0 h' would be a lie and
    a huge number would be noise."""
    assert watch.human(float("nan")) == "unknown"
    assert watch.human(0) == "unknown"
    assert watch.human(10_000) == "unknown"
    assert watch.human(11.97) == "11 h 58 min"
    assert watch.human(0.5) == "30 min"
    assert watch.human(3.0) == "3 h"
