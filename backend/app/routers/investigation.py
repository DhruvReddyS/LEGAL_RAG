"""Investigation timeline for a police matter.

Deterministic throughout: the handler does date arithmetic against the BNSS
and returns it. There is no model call here, and adding one would defeat
the point -- these dates decide whether a person is lawfully in custody.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.permissions import POLICE_INVESTIGATION_OWN
from app.core.rbac import require_permission
from app.models import AuditLog, InvestigationFacts as InvestigationFactsRow, User
from app.schemas.investigation import (
    DeadlineResponse,
    InvestigationFactsResponse,
    InvestigationTimelineRequest,
    InvestigationTimelineResponse,
)
from app.services.investigation_timeline import (
    InvestigationFacts,
    breached,
    investigation_deadlines,
    undetermined,
)

router = APIRouter(prefix="/cases/{case_id}/investigation", tags=["police-investigation"])


@router.post("/timeline", response_model=InvestigationTimelineResponse)
async def compute_timeline(
    case_id: uuid.UUID,
    request: InvestigationTimelineRequest,
    current_user: Annotated[
        User,
        Depends(require_permission(POLICE_INVESTIGATION_OWN, case_id_param="case_id")),
    ],
    session: AsyncSession = Depends(get_db_session),
) -> InvestigationTimelineResponse:
    facts = InvestigationFacts(**request.model_dump())
    now = datetime.now(timezone.utc)
    deadlines = investigation_deadlines(facts)

    session.add(
        AuditLog(
            user_id=current_user.id,
            action="police.investigation_timeline",
            resource_type="case",
            resource_id=case_id,
            metadata_={
                "deadline_count": len(deadlines),
                "breached": [d.key for d in breached(deadlines, now)],
                "undetermined": [d.key for d in undetermined(deadlines)],
            },
        )
    )
    await session.commit()

    return InvestigationTimelineResponse(
        evaluated_at=now,
        deadlines=[
            DeadlineResponse(
                key=d.key,
                obligation=d.obligation,
                provision=d.provision,
                due_at=d.due_at,
                consequence=d.consequence,
                computed_from=d.computed_from,
                is_earliest_possible=d.is_earliest_possible,
                undetermined_because=d.undetermined_because,
                is_breached=d.is_breached(now),
            )
            for d in deadlines
        ],
        breached=[d.key for d in breached(deadlines, now)],
        undetermined=[d.key for d in undetermined(deadlines)],
    )


_FACT_FIELDS = (
    "information_recorded_at",
    "arrested_at",
    "first_remand_at",
    "accused_produced_at",
    "death_occurred_at",
    "preliminary_enquiry_started_at",
    "gravity",
    "is_listed_sexual_offence",
    "is_unnatural_death",
)


def _timeline_from(facts: InvestigationFacts, now: datetime) -> InvestigationTimelineResponse:
    deadlines = investigation_deadlines(facts)
    return InvestigationTimelineResponse(
        evaluated_at=now,
        deadlines=[
            DeadlineResponse(
                key=d.key,
                obligation=d.obligation,
                provision=d.provision,
                due_at=d.due_at,
                consequence=d.consequence,
                computed_from=d.computed_from,
                is_earliest_possible=d.is_earliest_possible,
                undetermined_because=d.undetermined_because,
                is_breached=d.is_breached(now),
            )
            for d in deadlines
        ],
        breached=[d.key for d in breached(deadlines, now)],
        undetermined=[d.key for d in undetermined(deadlines)],
    )


async def _row_for(session: AsyncSession, case_id: uuid.UUID) -> InvestigationFactsRow | None:
    return await session.scalar(
        select(InvestigationFactsRow).where(InvestigationFactsRow.case_id == case_id)
    )


@router.put("/facts", response_model=InvestigationFactsResponse)
async def record_facts(
    case_id: uuid.UUID,
    request: InvestigationTimelineRequest,
    current_user: Annotated[
        User,
        Depends(require_permission(POLICE_INVESTIGATION_OWN, case_id_param="case_id")),
    ],
    session: AsyncSession = Depends(get_db_session),
) -> InvestigationFactsResponse:
    """Record what is known about this matter.

    A full replace, not a merge. A partial update would make clearing a
    wrongly entered arrest time impossible to express: sending null would be
    indistinguishable from not sending the field, and the wrong date would
    stay on record and keep producing a deadline.
    """
    submitted = request.model_dump()
    row = await _row_for(session, case_id)
    if row is None:
        row = InvestigationFactsRow(case_id=case_id)
        session.add(row)
    for field in _FACT_FIELDS:
        setattr(row, field, submitted[field])

    session.add(
        AuditLog(
            user_id=current_user.id,
            action="police.investigation_facts_recorded",
            resource_type="case",
            resource_id=case_id,
            metadata_={
                "fields_set": [f for f in _FACT_FIELDS if submitted[f] not in (None, False)],
            },
        )
    )
    await session.commit()
    await session.refresh(row)

    return InvestigationFactsResponse(
        case_id=case_id,
        updated_at=row.updated_at,
        **{field: getattr(row, field) for field in _FACT_FIELDS},
    )


@router.get("/facts", response_model=InvestigationFactsResponse)
async def read_facts(
    case_id: uuid.UUID,
    current_user: Annotated[
        User,
        Depends(require_permission(POLICE_INVESTIGATION_OWN, case_id_param="case_id")),
    ],
    session: AsyncSession = Depends(get_db_session),
) -> InvestigationFactsResponse:
    row = await _row_for(session, case_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No investigation facts recorded for this case",
        )
    return InvestigationFactsResponse(
        case_id=case_id,
        updated_at=row.updated_at,
        **{field: getattr(row, field) for field in _FACT_FIELDS},
    )


@router.get("/timeline", response_model=InvestigationTimelineResponse)
async def stored_timeline(
    case_id: uuid.UUID,
    current_user: Annotated[
        User,
        Depends(require_permission(POLICE_INVESTIGATION_OWN, case_id_param="case_id")),
    ],
    session: AsyncSession = Depends(get_db_session),
) -> InvestigationTimelineResponse:
    """The timeline from what is on record.

    404 rather than an empty schedule when nothing is recorded. An empty
    schedule reads as "no deadlines apply to this matter", which is a
    finding; "nothing has been recorded yet" is not.
    """
    row = await _row_for(session, case_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No investigation facts recorded for this case",
        )
    facts = InvestigationFacts(
        **{field: getattr(row, field) for field in _FACT_FIELDS}
    )
    return _timeline_from(facts, datetime.now(timezone.utc))
