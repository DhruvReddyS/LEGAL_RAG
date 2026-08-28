from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


RequestedMode = Literal["auto", "fast", "deep"]
SelectedMode = Literal["fast", "deep"]


DEEP_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("defence_strategy", re.compile(r"\b(defen[cs]e|defending|loopholes?|counterarguments?|weaknesses?)\b", re.I)),
    ("case_analysis", re.compile(r"\b(case scenario|fact pattern|analyse the case|analyze the case|case strategy)\b", re.I)),
    ("evidence_analysis", re.compile(r"\b(contradictions?|cross[- ]examination|chain of custody|evidence matrix)\b", re.I)),
    ("comparative_reasoning", re.compile(r"\b(compare|distinguish|both sides|pros and cons|arguments? for and against)\b", re.I)),
    ("legal_drafting", re.compile(r"\b(draft|prepare|write)\b.{0,32}\b(FIR|petition|application|notice|reply|argument|submission)\b", re.I)),
    ("precedent_reasoning", re.compile(r"\b(precedents?|case law)\b.{0,40}\b(apply|analyse|analyze|distinguish|compare)\b", re.I)),
    ("constitutional_applicability", re.compile(r"\b(private employer|private actor|state action|horizontal application|directly appl(?:y|ies))\b", re.I)),
)


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    requested_mode: RequestedMode
    selected_mode: SelectedMode
    reason: str
    signals: tuple[str, ...]


def route_legal_query(*, query: str, requested_mode: RequestedMode, case_id: object | None = None) -> RoutingDecision:
    """Select the smallest safe workflow without using an LLM in the routing path."""

    if requested_mode in {"fast", "deep"}:
        return RoutingDecision(
            requested_mode=requested_mode,
            selected_mode=requested_mode,
            reason="user_selected",
            signals=(f"explicit_{requested_mode}_mode",),
        )

    signals: list[str] = []
    if case_id is not None:
        signals.append("case_scoped_matter")

    for signal, pattern in DEEP_PATTERNS:
        if pattern.search(query):
            signals.append(signal)

    word_count = len(re.findall(r"\b\w+\b", query))
    if word_count >= 36:
        signals.append("long_multi_fact_query")
    if query.count("?") >= 2:
        signals.append("multiple_questions")
    if len(re.findall(r"\b(?:section|article|rule|order)\s+\w+", query, re.I)) >= 2:
        signals.append("multiple_legal_provisions")

    if signals:
        return RoutingDecision(
            requested_mode="auto",
            selected_mode="deep",
            reason="complex_analysis_required",
            signals=tuple(dict.fromkeys(signals)),
        )

    return RoutingDecision(
        requested_mode="auto",
        selected_mode="fast",
        reason="focused_authority_lookup",
        signals=("simple_focused_query",),
    )
