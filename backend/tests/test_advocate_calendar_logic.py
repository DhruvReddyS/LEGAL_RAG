"""Calendar states and limitation arithmetic. Pure; no database."""

from __future__ import annotations

from datetime import date

import pytest

from app.services.advocate_provisions import PROVISIONS
from app.services.matter_calendar import (
    LIMITATION_ARTICLES,
    EventState,
    article_catalogue,
    compute_limitation,
    event_state,
)

TODAY = date(2026, 11, 4)


@pytest.mark.parametrize(
    ("due", "completed", "expected"),
    [
        (date(2026, 11, 3), False, EventState.OVERDUE),
        (date(2026, 11, 4), False, EventState.DUE_TODAY),
        (date(2026, 11, 5), False, EventState.DUE_SOON),
        (date(2026, 11, 11), False, EventState.DUE_SOON),
        (date(2026, 11, 12), False, EventState.UPCOMING),
        (date(2020, 1, 1), True, EventState.DONE),
    ],
)
def test_event_states(due, completed, expected):
    assert event_state(due, completed=completed, today=TODAY) is expected


class TestLimitation:
    def test_days_exclude_the_day_of_reckoning(self):
        assert compute_limitation("art_116_b", date(2026, 3, 1))["last_day"] == "2026-03-31"

    def test_years_land_on_the_same_date(self):
        assert compute_limitation("art_113", date(2026, 1, 15))["last_day"] == "2029-01-15"

    def test_a_leap_day_clamps(self):
        assert compute_limitation("art_113", date(2024, 2, 29))["last_day"] == "2027-02-28"

    def test_excluded_days_extend_the_date(self):
        assert compute_limitation("art_116_a", date(2026, 1, 1), excluded_days=10)["last_day"] == "2026-04-11"

    def test_a_negative_exclusion_is_refused(self):
        with pytest.raises(ValueError):
            compute_limitation("art_113", TODAY, excluded_days=-1)

    def test_an_article_that_is_not_pinned_gets_no_date(self):
        with pytest.raises(KeyError):
            compute_limitation("art_999", TODAY)

    def test_it_cites_the_article_and_shows_its_working(self):
        result = compute_limitation("art_137", TODAY)
        sections = {source["section"] for source in result["sources"]}
        assert "Limitation Act, Schedule, Art. 137" in sections
        assert "Limitation Act s.12(1)" in sections
        assert any("s.12(1)" in step for step in result["steps"])

    def test_it_says_what_it_did_not_apply(self):
        result = compute_limitation("art_116_a", TODAY)
        joined = " ".join(result["not_applied"])
        assert "s.4" in joined and "special or local law" in joined and "certified copy" in joined

    def test_articles_written_against_the_old_code_say_so(self):
        for key in ("art_114_a", "art_115_b_i", "art_131"):
            assert "1898" in compute_limitation(key, TODAY)["caution"]

    def test_every_article_is_pinned_and_its_period_is_in_the_quoted_text(self):
        words = {
            (3, "years"): "Three years", (12, "years"): "Twelve years", (90, "days"): "Ninety days",
            (60, "days"): "Sixty days", (30, "days"): "Thirty days", (10, "days"): "Ten days",
        }
        for article in LIMITATION_ARTICLES:
            quote = PROVISIONS[article.provision].quote
            assert words[(article.amount, article.unit)] in quote, article.key

    def test_the_catalogue_offers_only_what_it_can_compute(self):
        for row in article_catalogue():
            assert compute_limitation(row["key"], TODAY)["article"] == row["article"]
