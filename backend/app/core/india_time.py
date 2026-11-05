"""What day and hour it is where the officer, the advocate and the court are.

Timestamps are stored as instants, in UTC. A printed record and a day count both have
to read them in India's time: 18:00 on the 4th is 12:30 UTC, and 00:30 on the 5th is
still the 4th in UTC, which moves a statutory window by a day.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

INDIA = ZoneInfo("Asia/Kolkata")


def india_today() -> date:
    return datetime.now(INDIA).date()


def india_date(moment: datetime) -> date:
    """The calendar date of an instant in India. A naive value is taken as already local."""
    return moment.astimezone(INDIA).date() if moment.tzinfo else moment.date()


def india_moment_text(moment: datetime) -> str:
    """For a printed record, which has no browser to localise it and must say whose clock."""
    if moment.tzinfo is None:
        return moment.strftime("%d %b %Y, %H:%M")
    return moment.astimezone(INDIA).strftime("%d %b %Y, %H:%M IST")
