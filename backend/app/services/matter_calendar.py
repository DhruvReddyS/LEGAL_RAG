"""Hearing and limitation dates: their state today, and limitation arithmetic.

The limitation calculation carries real liability, so it follows the rule the
product doc sets for it: every result cites the Schedule article, shows how the
date was reached, and names what it did not take into account. Only articles
pinned to the corpus text can be chosen. A proceeding that fits none of them
gets no date from this module, rather than a guess at the nearest one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from typing import Any

from app.services.advocate_provisions import provision_sources
from app.services.investigation_timeline import add_calendar_months

DUE_SOON_DAYS = 7


class EventState(StrEnum):
    DONE = "done"
    OVERDUE = "overdue"
    DUE_TODAY = "due_today"
    DUE_SOON = "due_soon"
    UPCOMING = "upcoming"


def event_state(due_on: date, *, completed: bool, today: date) -> EventState:
    """Completion wins: a date dealt with is not overdue, however old it is."""
    if completed:
        return EventState.DONE
    if due_on < today:
        return EventState.OVERDUE
    if due_on == today:
        return EventState.DUE_TODAY
    if due_on <= today + timedelta(days=DUE_SOON_DAYS):
        return EventState.DUE_SOON
    return EventState.UPCOMING


@dataclass(frozen=True)
class LimitationArticle:
    key: str
    article: str
    description: str
    division: str
    amount: int
    unit: str  # days | months | years
    runs_from: str
    provision: str
    caution: str = ""

    @property
    def period(self) -> str:
        return f"{self.amount} {self.unit}"


_OLD_CODE = (
    "The Schedule in the corpus still names the Code of Criminal Procedure, 1898 here. Confirm "
    "how it applies to a proceeding under the BNSS, and whether the BNSS or a special Act fixes "
    "its own period, before relying on this date."
)

LIMITATION_ARTICLES: tuple[LimitationArticle, ...] = (
    LimitationArticle("art_54", "Art. 54", "Specific performance of a contract", "Suits", 3, "years",
                      "the date fixed for performance or, if none, when the plaintiff has notice that performance is refused", "lim_art_54"),
    LimitationArticle("art_55", "Art. 55", "Compensation for breach of contract", "Suits", 3, "years",
                      "when the contract is broken, subject to the article's words on successive and continuing breaches", "lim_art_55"),
    LimitationArticle("art_58", "Art. 58", "Any other declaration", "Suits", 3, "years",
                      "when the right to sue first accrues", "lim_art_58"),
    LimitationArticle("art_59", "Art. 59", "To cancel or set aside an instrument or decree, or rescind a contract", "Suits", 3, "years",
                      "when the facts entitling the plaintiff first become known to him", "lim_art_59"),
    LimitationArticle("art_65", "Art. 65", "Possession of immovable property based on title", "Suits", 12, "years",
                      "when the defendant's possession becomes adverse to the plaintiff", "lim_art_65"),
    LimitationArticle("art_113", "Art. 113", "Any suit with no period elsewhere in the Schedule", "Suits", 3, "years",
                      "when the right to sue accrues", "lim_art_113"),
    LimitationArticle("art_114_a", "Art. 114(a)", "Appeal from acquittal, under s.417(1) or (2) of the 1898 Code", "Appeals", 90, "days",
                      "the date of the order appealed from", "lim_art_114_a", _OLD_CODE),
    LimitationArticle("art_114_b", "Art. 114(b)", "Appeal from acquittal, under s.417(3) of the 1898 Code", "Appeals", 30, "days",
                      "the date of the grant of special leave", "lim_art_114_b", _OLD_CODE),
    LimitationArticle("art_115_a", "Art. 115(a)", "Criminal appeal from a sentence of death", "Appeals", 30, "days",
                      "the date of the sentence", "lim_art_115_a", _OLD_CODE),
    LimitationArticle("art_115_b_i", "Art. 115(b)(i)", "Criminal appeal to the High Court, other sentence or order", "Appeals", 60, "days",
                      "the date of the sentence or order", "lim_art_115_b_i", _OLD_CODE),
    LimitationArticle("art_115_b_ii", "Art. 115(b)(ii)", "Criminal appeal to any other court, other sentence or order", "Appeals", 30, "days",
                      "the date of the sentence or order", "lim_art_115_b_ii", _OLD_CODE),
    LimitationArticle("art_116_a", "Art. 116(a)", "CPC appeal to a High Court", "Appeals", 90, "days",
                      "the date of the decree or order", "lim_art_116_a"),
    LimitationArticle("art_116_b", "Art. 116(b)", "CPC appeal to any other court", "Appeals", 30, "days",
                      "the date of the decree or order", "lim_art_116_b"),
    LimitationArticle("art_117", "Art. 117", "From a High Court decree or order to the same Court", "Appeals", 30, "days",
                      "the date of the decree or order", "lim_art_117"),
    LimitationArticle("art_118", "Art. 118", "Leave to appear and defend a summary suit", "Applications", 10, "days",
                      "when the summons is served", "lim_art_118"),
    LimitationArticle("art_123", "Art. 123", "To set aside an ex parte decree or rehear an appeal", "Applications", 30, "days",
                      "the date of the decree or, where summons was not duly served, knowledge of the decree", "lim_art_123"),
    LimitationArticle("art_124", "Art. 124", "Review of judgment by a court other than the Supreme Court", "Applications", 30, "days",
                      "the date of the decree or order", "lim_art_124"),
    LimitationArticle("art_131", "Art. 131", "Revision under the CPC or the 1898 Code", "Applications", 90, "days",
                      "the date of the decree, order or sentence sought to be revised", "lim_art_131", _OLD_CODE),
    LimitationArticle("art_137", "Art. 137", "Any other application with no period elsewhere in the Division", "Applications", 3, "years",
                      "when the right to apply accrues", "lim_art_137"),
)
_BY_KEY = {article.key: article for article in LIMITATION_ARTICLES}
_APPEAL_DIVISIONS = {"Appeals"}


def article_catalogue() -> list[dict[str, Any]]:
    return [
        {
            "key": item.key,
            "article": item.article,
            "description": item.description,
            "division": item.division,
            "period": item.period,
            "runs_from": item.runs_from,
            "caution": item.caution,
        }
        for item in LIMITATION_ARTICLES
    ]


def _add_period(start: date, amount: int, unit: str) -> date:
    if unit == "days":
        return start + timedelta(days=amount)
    months = amount * 12 if unit == "years" else amount
    return add_calendar_months(start, months)


def compute_limitation(article_key: str, runs_from: date, *, excluded_days: int = 0) -> dict[str, Any]:
    """The last day of the period under one Schedule article.

    Under s.12(1) the day the period is reckoned from is excluded, which is
    why thirty days from 1 March is 31 March and three years from 15 January
    2026 is 15 January 2029.
    """
    article = _BY_KEY.get(article_key)
    if article is None:
        raise KeyError(article_key)
    if excluded_days < 0:
        raise ValueError("excluded_days cannot be negative")
    computed = _add_period(runs_from, article.amount, article.unit)
    last_day = computed + timedelta(days=excluded_days)
    steps = [
        f"{article.article}: {article.period}, running from {article.runs_from}.",
        f"You entered {runs_from.isoformat()} as that date. Whether it is the right starting point is your assessment; it is not checked.",
        "s.12(1): the day from which the period is reckoned is excluded.",
    ]
    if excluded_days:
        steps.append(f"{excluded_days} day(s) you entered as excluded are added.")
    sources = ["lim_3_1", article.provision, "lim_12_1", "lim_4"]
    not_applied = [
        "Whether the last day falls when the court is closed (s.4): court holidays are not known here.",
        "Any exclusion or extension under ss.6 to 8 or ss.13 to 19, unless you entered it as excluded days.",
        "Any different period under a special or local law, or under the Act the proceeding arises from.",
    ]
    if article.division in _APPEAL_DIVISIONS or article.key in {"art_124", "art_131"}:
        sources.append("lim_12_2")
        not_applied.append(
            "Time to obtain a certified copy under s.12(2) and (3), unless you entered it as excluded days."
        )
        sources.append("lim_5")
    return {
        "article": article.article,
        "description": article.description,
        "period": article.period,
        "runs_from": runs_from.isoformat(),
        "excluded_days": excluded_days,
        "last_day": last_day.isoformat(),
        "steps": steps,
        "not_applied": not_applied,
        "caution": article.caution,
        "sources": provision_sources(*sources),
        "basis_label": f"Limitation Act, Schedule, {article.article}",
    }
