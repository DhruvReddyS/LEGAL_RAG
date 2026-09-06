"""What the answer is worth, measured rather than eyeballed.

Retrieval evaluation says the right passage was found. It says nothing about
whether the answer used it, whether the answer named every ground the statute
enumerates, whether it flagged that its authority has been repealed, or
whether a citizen can read it. Those are separate failures, and until now the
only instrument for them was reading answers by hand.

Every metric here is deterministic: given a finished workflow state, it
returns the same numbers on every run. Nothing calls a model. That matters
because these numbers gate merges, and a gate that drifts on its own is not
a gate.

The metrics deliberately do not average into a single score. An answer that
is beautifully readable and cites a repealed section is not "70% good"; it
is wrong in a specific way, and collapsing it into one number hides which.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from app.schemas.agents import ClaimVerification, VerificationResult
from app.services.currency import CurrencyStatus, resolve_currency
from app.services.generation import INSUFFICIENT_EVIDENCE
from app.services.repeal_labels import RepealLabel, repeal_notice

__all__ = [
    "AnswerQuality",
    "GroundExpectation",
    "abstained",
    "assess_answer",
    "currency_assessment",
    "ground_coverage",
    "reading_grade",
    "unsupported_claims",
]


# ---------------------------------------------------------------- abstention


def abstained(state: Mapping[str, Any]) -> bool:
    """Did the run refuse to answer?

    The pipeline has exactly one way of saying so, and this reads that one
    way rather than guessing from an empty citation list -- an answer can
    legitimately cite nothing and still be an answer.
    """
    answer = str(state.get("final_answer") or "")
    return not answer.strip() or answer.strip() == INSUFFICIENT_EVIDENCE.strip()


# ------------------------------------------------------- unsupported claims


def _retrieved_chunk_ids(state: Mapping[str, Any]) -> set[str]:
    ids: set[str] = set()
    for hit in state.get("retrieved_chunks") or []:
        payload = getattr(hit, "payload", None) or {}
        chunk_id = payload.get("chunk_id") or getattr(hit, "point_id", None)
        if chunk_id:
            ids.add(str(chunk_id))
    return ids


def _published_claims(state: Mapping[str, Any]) -> list[ClaimVerification]:
    """The claims that actually reached the reader.

    Only ``yes`` verdicts are published, so a ``no`` claim sitting in the
    verification result is the system working, not a defect. Counting those
    as unsupported would report a violation every time verification did its
    job.
    """
    result = state.get("verification_result")
    if not isinstance(result, VerificationResult):
        return []
    return [claim for claim in result.claims if claim.verdict == "yes"]


def unsupported_claims(state: Mapping[str, Any]) -> list[ClaimVerification]:
    """Published claims whose evidence was never retrieved.

    This is the standing rule -- never publish a claim whose chunk IDs are
    not in the retrieved set -- turned into a number. It should be zero on
    every run. A non-zero value is not a quality regression to weigh against
    others; it means the pipeline published something it could not show.
    """
    retrieved = _retrieved_chunk_ids(state)
    return [claim for claim in _published_claims(state) if claim.chunk_id not in retrieved]


# ------------------------------------------------------------------ currency


@dataclass(frozen=True)
class CurrencyAssessment:
    """Whether the answer said what the resolver says it must.

    ``required`` counts cited sources that carry a currency obligation --
    either the authority itself is no longer in force, or it construes a
    provision that has since moved. ``satisfied`` counts those the answer
    actually disclosed. The two must be equal.
    """

    required: int = 0
    satisfied: int = 0
    missing: tuple[str, ...] = ()

    @property
    def correct(self) -> bool:
        return self.required == self.satisfied

    @property
    def rate(self) -> float | None:
        if not self.required:
            return None
        return self.satisfied / self.required


def currency_assessment(state: Mapping[str, Any]) -> CurrencyAssessment:
    """Compare the answer against the deterministic currency resolver.

    The resolver, not the model, decides what the obligation is. The answer
    is then checked for having discharged it. Doing it the other way round --
    reading the answer and asking whether it looks careful -- is how a
    fluent answer about a repealed section passes review.
    """
    answer = str(state.get("final_answer") or "")
    if abstained(state):
        return CurrencyAssessment()

    hit_by_id = {}
    for hit in state.get("retrieved_chunks") or []:
        payload = getattr(hit, "payload", None) or {}
        chunk_id = payload.get("chunk_id")
        if chunk_id:
            hit_by_id[str(chunk_id)] = payload

    cited = {str(getattr(c, "chunk_id", "")) for c in state.get("citations") or []}
    required = 0
    satisfied = 0
    missing: list[str] = []

    for chunk_id in sorted(cited):
        payload = hit_by_id.get(chunk_id)
        if not payload or payload.get("corpus_scope") == "private_case":
            continue

        decision = resolve_currency(payload)
        if decision.status is CurrencyStatus.SUPERSEDED:
            required += 1
            name = str(payload.get("act_name") or payload.get("title") or "")
            # The disclosure names the Act and says it was replaced. Match on
            # the Act's own name so a generic "some sources may be outdated"
            # does not count as having said it.
            if name and name.lower() in answer.lower() and "no longer in force" in answer.lower():
                satisfied += 1
            else:
                missing.append(f"{chunk_id}: superseded Act {name!r} not disclosed")

        notice = repeal_notice(payload)
        if notice.label is RepealLabel.CONCERNS_REPEALED_PROVISION and notice.mappings:
            for mapping in notice.mappings:
                required += 1
                moved = f"{mapping.to_code} s.{mapping.to_section}".lower()
                if moved in answer.lower():
                    satisfied += 1
                else:
                    missing.append(
                        f"{chunk_id}: {mapping.from_code} s.{mapping.from_section} "
                        f"-> {mapping.to_code} s.{mapping.to_section} not disclosed"
                    )

    return CurrencyAssessment(required=required, satisfied=satisfied, missing=tuple(missing))


# ------------------------------------------------------------- reading level


_SENTENCE_END = re.compile(r"[.!?]+(?:\s|$)")
_WORD = re.compile(r"[A-Za-z][A-Za-z'’\-]*")
_VOWEL_RUN = re.compile(r"[aeiouy]+")
_MARKDOWN = re.compile(r"^\s{0,3}(#{1,6}\s|[-*]\s|\d+\.\s|>|\||---)", re.M)


def _syllables(word: str) -> int:
    """Vowel-run count with the silent-terminal-e correction.

    A dictionary would be more accurate and would also make the metric
    depend on a data file that can go missing. This is stable, offline, and
    good enough for a trend -- which is all a reading grade is used for here.
    """
    lowered = word.lower()
    runs = len(_VOWEL_RUN.findall(lowered))
    if lowered.endswith("e") and not lowered.endswith(("le", "ee", "ye")) and runs > 1:
        runs -= 1
    return max(runs, 1)


def reading_grade(text: str) -> float | None:
    """Flesch-Kincaid grade level of the prose in an answer.

    Two caveats worth stating rather than burying. Markdown scaffolding is
    stripped first, because a heading is not a sentence and counting it as
    one halves the apparent sentence length. And statutory prose is
    polysyllabic by nature -- "Bharatiya Nagarik Suraksha Sanhita" alone is
    eleven syllables -- so the absolute figure runs high for any correct
    legal answer. Read it as a trend against the same corpus, not as a
    claim that a citizen needs a given number of years of schooling.
    """
    prose = _MARKDOWN.sub("", text or "")
    prose = re.sub(r"\[Source \d+\]", "", prose)
    prose = re.sub(r"[*_`]", "", prose).strip()
    if not prose:
        return None

    words = _WORD.findall(prose)
    if not words:
        return None
    sentences = max(len(_SENTENCE_END.findall(prose)), 1)
    syllables = sum(_syllables(word) for word in words)

    grade = (
        0.39 * (len(words) / sentences)
        + 11.8 * (syllables / len(words))
        - 15.59
    )
    return round(grade, 1)


# ----------------------------------------------------------- ground coverage


@dataclass(frozen=True)
class GroundExpectation:
    """One thing a correct answer to this question has to say.

    ``any_of`` holds alternative surface forms for the same ground, because
    the answer may say "cognizable offence" or "cognisable offence" and both
    are the same ground. It does not hold *different* grounds -- each of
    those gets its own expectation, or coverage silently rewards naming one
    of five.
    """

    name: str
    any_of: tuple[str, ...]

    def satisfied_by(self, answer: str) -> bool:
        lowered = answer.lower()
        return any(form.lower() in lowered for form in self.any_of)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "GroundExpectation":
        forms = payload.get("any_of") or [payload["name"]]
        return cls(name=str(payload["name"]), any_of=tuple(str(f) for f in forms))


def ground_coverage(
    answer: str, expectations: Sequence[GroundExpectation]
) -> tuple[float | None, tuple[str, ...]]:
    """Fraction of the required grounds the answer actually names.

    Returns the fraction and the names of the ones it missed, because the
    fraction alone tells you a run got worse without telling you what fell
    out -- and the missing ground is the whole finding.
    """
    if not expectations:
        return None, ()
    missed = tuple(e.name for e in expectations if not e.satisfied_by(answer))
    return (len(expectations) - len(missed)) / len(expectations), missed


# ------------------------------------------------------------------ assembly


@dataclass(frozen=True)
class AnswerQuality:
    """Every metric for one question, kept separate on purpose."""

    item_id: str
    role: str
    expectation: str
    did_abstain: bool
    abstention_correct: bool
    published_claim_count: int
    unsupported_claim_count: int
    unsupported_claim_details: tuple[str, ...]
    currency: CurrencyAssessment
    reading_grade: float | None
    ground_coverage: float | None
    grounds_missed: tuple[str, ...]

    def as_row(self) -> dict[str, Any]:
        return {
            "id": self.item_id,
            "role": self.role,
            "expectation": self.expectation,
            "abstained": self.did_abstain,
            "abstention_correct": self.abstention_correct,
            "published_claims": self.published_claim_count,
            "unsupported_claims": self.unsupported_claim_count,
            "unsupported_claim_details": list(self.unsupported_claim_details),
            "currency_required": self.currency.required,
            "currency_satisfied": self.currency.satisfied,
            "currency_correct": self.currency.correct,
            "currency_missing": list(self.currency.missing),
            "reading_grade": self.reading_grade,
            "ground_coverage": self.ground_coverage,
            "grounds_missed": list(self.grounds_missed),
        }


def assess_answer(
    state: Mapping[str, Any],
    *,
    item_id: str,
    role: str,
    expectation: str,
    grounds: Iterable[Mapping[str, Any]] = (),
) -> AnswerQuality:
    """Measure one finished run against what was expected of it."""
    answer = str(state.get("final_answer") or "")
    did_abstain = abstained(state)
    expected_abstention = expectation == "abstain"

    unsupported = unsupported_claims(state)
    expectations = [GroundExpectation.from_payload(g) for g in grounds]
    # An abstention names no grounds, and scoring it 0.0 would make abstaining
    # correctly look identical to answering badly. It gets no coverage score.
    coverage, missed = (None, ()) if did_abstain else ground_coverage(answer, expectations)

    return AnswerQuality(
        item_id=item_id,
        role=role,
        expectation=expectation,
        did_abstain=did_abstain,
        abstention_correct=(did_abstain == expected_abstention),
        published_claim_count=len(_published_claims(state)),
        unsupported_claim_count=len(unsupported),
        unsupported_claim_details=tuple(
            f"{c.chunk_id}: {c.claim[:80]}" for c in unsupported
        ),
        currency=currency_assessment(state),
        reading_grade=None if did_abstain else reading_grade(answer),
        ground_coverage=coverage,
        grounds_missed=missed,
    )
