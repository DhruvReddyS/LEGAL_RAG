"""A case file printed an arrest at 18:00 as "12:30", unlabelled, for a court to read.

Everything stored is an instant in UTC. The Word and HTML exports printed it raw, and
day counts took the UTC date, so 00:30 on the 5th counted as the 4th.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import Path

from app.core.india_time import INDIA, india_date, india_moment_text
from app.models.enums import OffenceGravity
from app.services.police_case_file import _text
from app.services.police_custody import RemandPeriod, remand_summary
from app.services.police_drafting import _when

ROOT = Path(__file__).resolve().parents[1] / "app"
# 18:00 on the 4th in India.
ARREST = datetime(2026, 11, 4, 12, 30, tzinfo=timezone.utc)
# 00:30 on the 5th in India, still the 4th in UTC.
JUST_AFTER_MIDNIGHT = datetime(2026, 11, 5, 0, 30, tzinfo=INDIA)


def test_a_printed_record_says_india_time_and_says_whose_clock() -> None:
    assert _text(ARREST) == "04 Nov 2026, 18:00 IST"
    assert _when(ARREST) == "04 Nov 2026, 18:00 IST"
    assert _text(date(2026, 11, 4)) == "04 Nov 2026"
    assert _when(date(2026, 11, 4)) == "04 Nov 2026"


def test_a_utc_stored_instant_prints_the_same_as_the_india_one_it_is() -> None:
    assert india_moment_text(JUST_AFTER_MIDNIGHT.astimezone(timezone.utc)) == "05 Nov 2026, 00:30 IST"


def test_a_day_count_starts_on_the_india_date() -> None:
    assert india_date(JUST_AFTER_MIDNIGHT.astimezone(timezone.utc)) == date(2026, 11, 5)
    summary = remand_summary(
        [RemandPeriod("police", date(2026, 11, 5), date(2026, 11, 6))],
        first_remand_at=JUST_AFTER_MIDNIGHT.astimezone(timezone.utc),
        gravity=OffenceGravity.OTHER,
        today=date(2026, 11, 6),
    )
    assert summary.first_remand_date == date(2026, 11, 5)


def test_no_route_or_record_takes_today_from_utc() -> None:
    offenders = []
    for folder in ("routers", "services"):
        for path in (ROOT / folder).glob("*.py"):
            text = path.read_text()
            if re.search(r"now\(timezone\.utc\)\.date\(\)|date\.today\(\)", text) and path.name not in {
                "case_chronology.py",  # only the year, as a sanity bound on dates found in text
            }:
                offenders.append(path.name)
    assert offenders == []

