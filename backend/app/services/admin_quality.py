"""The answer-quality dashboard: stored evaluations and live telemetry.

Stored runs are measurements against the golden set. Live numbers describe what
users actually received. They measure different things and are kept apart, so a
chart never suggests one continues the other.

Live aggregation reads named numeric fields out of JSON in SQL. It never loads a
stored answer into this process, and nothing it returns is tied to a user.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import case, cast, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, ChatMessage, Feedback, Job
from app.models.enums import ChatMessageRole, FeedbackRating, JobStatus, JobType
from app.services.admin_evidence import list_evaluation_runs

MAX_TELEMETRY_ROWS = 5000
_TOTAL_TIMING_KEYS = ("api_total_ms", "workflow_total_ms", "total_ms")


def percentile(values: list[float], fraction: float) -> float | None:
    """Nearest-rank. With a handful of answers a day, interpolation invents precision."""
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(fraction * len(ordered) + 0.999999) - 1))
    return round(ordered[index], 1)


@dataclass(frozen=True)
class AnswerSignal:
    day: date
    abstained: bool
    unsupported: int | None
    latency_ms: float | None


def unsupported_from_metrics(metrics: Any) -> int | None:
    """Unsupported claims the verifier reported, across retries of this answer.

    The published answer drops them, so this counts what generation tried to say
    rather than what reached the reader. None when no verification ran: a Fast
    answer has none, and that must not read as zero.
    """
    if not isinstance(metrics, list):
        return None
    counts = [
        item.get("outputs", {}).get("unsupported_claim_count")
        for item in metrics
        if isinstance(item, dict) and item.get("stage") == "verification"
    ]
    counts = [count for count in counts if isinstance(count, int)]
    return counts[-1] if counts else None


def total_latency_ms(timings: Any) -> float | None:
    if not isinstance(timings, dict):
        return None
    for key in _TOTAL_TIMING_KEYS:
        value = timings.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None


def aggregate_days(
    signals: Iterable[AnswerSignal],
    citation_days: dict[date, tuple[int, int]],
    feedback_days: dict[date, tuple[int, int]],
) -> list[dict[str, Any]]:
    grouped: dict[date, list[AnswerSignal]] = defaultdict(list)
    for signal in signals:
        grouped[signal.day].append(signal)
    days = sorted(set(grouped) | set(citation_days) | set(feedback_days))
    rows = []
    for day in days:
        answers = grouped.get(day, [])
        latencies = [item.latency_ms for item in answers if item.latency_ms is not None]
        verified = [item.unsupported for item in answers if item.unsupported is not None]
        with_citations, assistant = citation_days.get(day, (0, 0))
        down, rated = feedback_days.get(day, (0, 0))
        rows.append(
            {
                "day": day.isoformat(),
                "answers": len(answers),
                "abstention_rate": (
                    round(sum(1 for item in answers if item.abstained) / len(answers), 3)
                    if answers
                    else None
                ),
                "citation_coverage": round(with_citations / assistant, 3) if assistant else None,
                "unsupported_claims": sum(verified) if verified else None,
                "verified_answers": len(verified),
                "latency_p50_ms": percentile(latencies, 0.5),
                "latency_p95_ms": percentile(latencies, 0.95),
                "feedback_down": down,
                "feedback_total": rated,
            }
        )
    return rows


async def _live_signals(session: AsyncSession, since: datetime) -> list[AnswerSignal]:
    chats = (
        await session.execute(
            select(
                AuditLog.timestamp,
                AuditLog.metadata_["evidence_strength"].astext,
                AuditLog.metadata_["pipeline_metrics"],
                AuditLog.metadata_["timings_ms"],
            )
            .where(AuditLog.action == "chat.query", AuditLog.timestamp >= since)
            .order_by(AuditLog.timestamp.desc())
            .limit(MAX_TELEMETRY_ROWS)
        )
    ).all()
    jobs = (
        await session.execute(
            select(
                Job.completed_at,
                Job.result["evidence_strength"].astext,
                Job.result["pipeline_metrics"],
                Job.started_at,
            )
            .where(
                Job.type == JobType.DEEP_REVIEW,
                Job.status == JobStatus.SUCCEEDED,
                Job.completed_at >= since,
            )
            .order_by(Job.completed_at.desc())
            .limit(MAX_TELEMETRY_ROWS)
        )
    ).all()
    signals = [
        AnswerSignal(
            day=stamp.astimezone(timezone.utc).date(),
            abstained=strength == "insufficient",
            unsupported=unsupported_from_metrics(metrics),
            latency_ms=total_latency_ms(timings),
        )
        for stamp, strength, metrics, timings in chats
    ]
    signals.extend(
        AnswerSignal(
            day=completed.astimezone(timezone.utc).date(),
            abstained=strength == "insufficient",
            unsupported=unsupported_from_metrics(metrics),
            latency_ms=(completed - started).total_seconds() * 1000 if started else None,
        )
        for completed, strength, metrics, started in jobs
    )
    return signals


async def live_quality(session: AsyncSession, days: int) -> dict[str, Any]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    signals = await _live_signals(session, since)

    message_day = func.date(func.timezone("UTC", ChatMessage.created_at))
    citation_rows = (
        await session.execute(
            select(
                message_day,
                func.sum(case((func.jsonb_array_length(cast(ChatMessage.citations, JSONB)) > 0, 1), else_=0)),
                func.count(ChatMessage.id),
            )
            .where(ChatMessage.role == ChatMessageRole.ASSISTANT, ChatMessage.created_at >= since)
            .group_by(message_day)
        )
    ).all()
    # `feedback` has no timestamp of its own, so a rating is dated by its answer.
    feedback_rows = (
        await session.execute(
            select(
                message_day,
                func.sum(case((Feedback.rating == FeedbackRating.DOWN, 1), else_=0)),
                func.count(Feedback.id),
            )
            .join(ChatMessage, ChatMessage.id == Feedback.message_id)
            .where(ChatMessage.created_at >= since)
            .group_by(message_day)
        )
    ).all()
    series = aggregate_days(
        signals,
        {row[0]: (int(row[1] or 0), int(row[2])) for row in citation_rows},
        {row[0]: (int(row[1] or 0), int(row[2])) for row in feedback_rows},
    )
    latencies = [item.latency_ms for item in signals if item.latency_ms is not None]
    verified = [item.unsupported for item in signals if item.unsupported is not None]
    assistant = sum(int(row[2]) for row in citation_rows)
    return {
        "days": days,
        "series": series,
        "totals": {
            "answers": len(signals),
            "abstention_rate": (
                round(sum(1 for item in signals if item.abstained) / len(signals), 3)
                if signals
                else None
            ),
            "citation_coverage": (
                round(sum(int(row[1] or 0) for row in citation_rows) / assistant, 3)
                if assistant
                else None
            ),
            "unsupported_claims": sum(verified) if verified else None,
            "verified_answers": len(verified),
            "latency_p50_ms": percentile(latencies, 0.5),
            "latency_p95_ms": percentile(latencies, 0.95),
            "feedback_down": sum(int(row[1] or 0) for row in feedback_rows),
            "feedback_total": sum(int(row[2]) for row in feedback_rows),
        },
    }


def stored_quality() -> dict[str, Any]:
    """Runs oldest first, so a chart reads left to right. Synchronous."""
    runs = list(reversed(list_evaluation_runs()))
    answer_keys = (
        "abstention_correct",
        "ground_coverage",
        "citation_coverage",
        "currency_correct",
        "unsupported_claims_total",
        "latency_p50_s",
    )
    retrieval_keys = (
        "recall_at_5",
        "citation_accuracy_at_5",
        "abstention_accuracy",
        "false_abstention_rate",
    )

    def points(kind: str, keys: tuple[str, ...]) -> list[dict[str, Any]]:
        return [
            {
                "id": run.id,
                "at": run.generated_at,
                "collection": run.collection,
                **{key: run.metrics.get(key) for key in keys},
            }
            for run in runs
            if run.kind == kind and run.generated_at
        ]

    return {
        "answers": points("answers", answer_keys),
        "retrieval": points("retrieval", retrieval_keys),
    }


async def quality_dashboard(session: AsyncSession, days: int) -> dict[str, Any]:
    stored, live = await asyncio.gather(asyncio.to_thread(stored_quality), live_quality(session, days))
    return {"stored": stored, "live": live}
