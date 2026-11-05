"""Dates a person could mean, checked before they are stored or calculated with.

A typed year of 9999 was accepted and stored, and the deadline arithmetic then
overflowed on every read: that case's timeline, the register and the case file all
failed until someone fixed the row by hand. The bounds are about arithmetic and typing
slips, not about what the law says.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, model_validator

EARLIEST_YEAR = 1900
LATEST_YEAR = 2200


class PlausibleDates(BaseModel):
    """Refuses any date field, at any nesting of this model's own fields, out of range."""

    @model_validator(mode="after")
    def _dates_are_plausible(self) -> Any:
        for name in type(self).model_fields:
            value = getattr(self, name)
            # datetime is a date too.
            if isinstance(value, date) and not EARLIEST_YEAR <= value.year <= LATEST_YEAR:
                raise ValueError(
                    f"{name}: the year must be between {EARLIEST_YEAR} and {LATEST_YEAR}"
                )
        return self
