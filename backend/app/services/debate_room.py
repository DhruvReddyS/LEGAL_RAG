"""The debate room: both sides in sequence, each statement verified, durably.

A run takes many sequential model calls and many minutes, so it runs as a durable
job. It survives a worker restart without paying twice: each completed turn is
checkpointed into the job's payload in its own transaction, and a retried attempt
carries on from the first unfinished turn. The turns published so far are readable
while the run is in progress, so nobody waits ten minutes looking at a percentage.

It never declares a winner. There is no field in the result for one.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from app.agents.advocate_agents import debate_turn
from app.core.database import AsyncSessionLocal
from app.models import Job
from app.models.enums import JobStatus
from app.services.advocate_sources import gather_evidence
from app.services.jobs import append_job_event, update_job_progress
from app.services.llm import OllamaClient
from app.services.retrieval import HybridRetrievalService

DEBATE_DISCLAIMER = (
    "Research aid for testing an argument. Each statement shown passed a check against the passage "
    "cited for it. This does not say which side is right or how a court would decide. Review every "
    "authority and its currency before relying on it."
)
SIDE_LABEL = {"for": "For the proposition", "against": "Against the proposition"}


class DebateStopped(Exception):
    """The job is no longer ours to run: cancelled, or claimed back."""


def turn_plan(rounds: int) -> list[tuple[int, str]]:
    return [(number, side) for number in range(1, rounds + 1) for side in ("for", "against")]


def assemble_debate(payload: dict[str, Any], turns: list[dict[str, Any]]) -> dict[str, Any]:
    verified = sum(len(turn["arguments"]) for turn in turns)
    proposed = sum(turn["proposed_count"] for turn in turns)
    repealed: dict[str, str] = {}
    for turn in turns:
        for argument in turn["arguments"]:
            for citation in argument["citations"]:
                if citation.get("repeal_label") == "no_longer_in_force":
                    repealed[citation["title"]] = citation.get("replaced_by") or ""
    return {
        "proposition": payload["proposition"],
        "facts": payload.get("facts"),
        "rounds": payload["rounds"],
        "turns": turns,
        "verified_count": verified,
        "proposed_count": proposed,
        "rejected_count": proposed - verified,
        "repealed_authorities": [
            {"title": title, "replaced_by": replaced or None} for title, replaced in repealed.items()
        ],
        "summary": (
            f"{verified} of {proposed} proposed arguments across {len(turns)} turns passed the check "
            "against their cited passages. The others are not shown."
        ),
        "disclaimer": DEBATE_DISCLAIMER,
    }


async def _progress(
    job_id: uuid.UUID,
    *,
    progress: int,
    stage: str,
    label: str,
    data: dict[str, Any] | None = None,
    checkpoint: list[dict[str, Any]] | None = None,
) -> None:
    async with AsyncSessionLocal() as session:
        async with session.begin():
            job = await session.scalar(
                select(Job)
                .where(Job.id == job_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if job is None or job.status is not JobStatus.RUNNING or job.cancel_requested:
                raise DebateStopped
            update_job_progress(job, min(99, max(job.progress, progress)))
            if checkpoint is not None:
                # A new dict, so SQLAlchemy sees the JSONB column change.
                job.payload = {**job.payload, "checkpoint": checkpoint}
            append_job_event(
                session,
                job,
                event_type="stage",
                stage=stage,
                data={"transition": "started", "label": label, **(data or {})},
            )


def _percent(done_turns: int, total: int, *, within: float = 0.0) -> int:
    return int(2 + 96 * (done_turns + within) / total)


async def run_debate(
    job_id: uuid.UUID,
    payload: dict[str, Any],
    *,
    retrieval: HybridRetrievalService,
    llm: OllamaClient,
) -> dict[str, Any]:
    """Run the turns still outstanding and return the assembled debate."""
    plan = turn_plan(int(payload["rounds"]))
    turns: list[dict[str, Any]] = list(payload.get("checkpoint") or [])
    proposition = str(payload["proposition"])
    facts = payload.get("facts")
    case_id = str(payload["case_id"])
    for position, (round_number, side) in enumerate(plan):
        if position < len(turns):
            continue
        name = f"Round {round_number}, {SIDE_LABEL[side].lower()}"
        stage = f"round_{round_number}_{side}"
        await _progress(job_id, progress=_percent(position, len(plan)), stage=stage, label=f"{name}: finding authority")
        opposing = [
            argument["text"]
            for turn in turns[-2:]
            if turn["side"] != side
            for argument in turn["arguments"]
        ]
        query = " ".join([proposition, facts or "", *opposing[:3]])
        evidence = await gather_evidence(retrieval, query, case_id=case_id)
        await _progress(
            job_id, progress=_percent(position, len(plan), within=0.15), stage=stage,
            label=f"{name}: drafting from {len(evidence.passages)} passages",
        )

        async def verifying(count: int, *, _stage: str = stage, _name: str = name, _position: int = position) -> None:
            await _progress(
                job_id, progress=_percent(_position, len(plan), within=0.6), stage=_stage,
                label=f"{_name}: checking {count} statement(s) against their sources",
            )

        turn = await debate_turn(
            llm,
            proposition=proposition,
            facts=facts,
            side=side,
            round_number=round_number,
            opposing=opposing,
            evidence=evidence,
            on_verifying=verifying,
        )
        turns.append(turn)
        await _progress(
            job_id, progress=_percent(position + 1, len(plan)), stage=stage,
            label=f"{name}: {len(turn['arguments'])} statement(s) passed",
            data={"verified": len(turn["arguments"]), "rejected": turn["rejected_count"]},
            checkpoint=turns,
        )
    return assemble_debate(payload, turns)
