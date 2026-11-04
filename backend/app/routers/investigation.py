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
    ComplianceChecklistResponse,
    ComplianceItemResponse,
    ComplianceUpdateRequest,
    DeadlineResponse,
    InvestigationFactsResponse,
    InvestigationTimelineRequest,
    InvestigationTimelineResponse,
)
from app.services.investigation_compliance import (
    ComplianceStatus,
    PoliceAction,
    compliance_checklist,
    outstanding,
    unrecorded,
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
                actor=d.actor,
                notes=list(d.notes),
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
    "is_custodial_death",
    "is_rape_or_attempt",
    "victim_examined_at",
    "arrested_under_warrant",
    "police_report_forwarded_at",
    "special_statute",
)

COMPLIANCE_FLAGS = (
    "arrested_person_is_woman",
    "handcuffs_used",
    "memorandum_attested_by_family",
    "bailable_arrest_without_warrant",
    "is_listed_sexual_offence",
    "electronic_device_seized",
)


def effective_flags(stored: dict | None, submitted: dict[str, bool | None]) -> dict[str, bool]:
    """What was asked for, falling back to what is on record, then to False."""
    known = stored or {}
    return {
        flag: bool(submitted[flag]) if submitted.get(flag) is not None else bool(known.get(flag))
        for flag in COMPLIANCE_FLAGS
    }


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
                actor=d.actor,
                notes=list(d.notes),
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
                "fields_set": [
                    f for f in _FACT_FIELDS if submitted[f] not in (None, False, "none", "unknown")
                ],
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


def _checklist_response(
    action: PoliceAction,
    stored: dict | None,
    flags: dict[str, bool],
) -> ComplianceChecklistResponse:
    recorded = {
        key: ComplianceStatus(value)
        for key, value in (stored or {}).items()
        # A key from an older shape of the checklist is dropped rather than
        # raising. Its requirement no longer exists, so its recorded status
        # is not about anything.
        if value in set(ComplianceStatus)
    }
    items = compliance_checklist(action, status=recorded, **flags)
    return ComplianceChecklistResponse(
        action=action,
        items=[
            ComplianceItemResponse(
                key=item.key,
                requirement=item.requirement,
                provision=item.provision,
                consequence=item.consequence,
                status=item.status,
                applies_because=item.applies_because,
            )
            for item in items
        ],
        outstanding=[item.key for item in outstanding(items)],
        not_recorded=[item.key for item in unrecorded(items)],
        flags=flags,
    )


@router.put("/compliance", response_model=ComplianceChecklistResponse)
async def record_compliance(
    case_id: uuid.UUID,
    request: ComplianceUpdateRequest,
    current_user: Annotated[
        User,
        Depends(require_permission(POLICE_INVESTIGATION_OWN, case_id_param="case_id")),
    ],
    session: AsyncSession = Depends(get_db_session),
) -> ComplianceChecklistResponse:
    """Record what has been confirmed for one action on this matter."""
    row = await _row_for(session, case_id)
    if row is None:
        row = InvestigationFactsRow(case_id=case_id)
        session.add(row)

    flags = effective_flags(
        row.compliance_flags, {flag: getattr(request, flag) for flag in COMPLIANCE_FLAGS}
    )
    row.compliance_flags = flags

    stored = dict(row.compliance_status or {})
    # Merged, not replaced. A conditional item is only listed while its flag is set,
    # so a flag switched off, or a save that does not name it, must not erase what
    # was recorded under it. Items this request's own flags list are replaced, since
    # leaving one out is how a mistaken tick is withdrawn.
    named = {flag: bool(getattr(request, flag)) for flag in COMPLIANCE_FLAGS}
    listed = {item.key for item in compliance_checklist(request.action, **named)}
    earlier = stored.get(str(request.action)) or {}
    stored[str(request.action)] = {
        **{key: value for key, value in earlier.items() if key not in listed},
        **{key: str(value) for key, value in request.status.items()},
    }
    row.compliance_status = stored

    session.add(
        AuditLog(
            user_id=current_user.id,
            action="police.compliance_recorded",
            resource_type="case",
            resource_id=case_id,
            metadata_={
                "police_action": str(request.action),
                "confirmed": sorted(
                    k for k, v in request.status.items()
                    if v is ComplianceStatus.SATISFIED
                ),
                "failed": sorted(
                    k for k, v in request.status.items()
                    if v is ComplianceStatus.NOT_SATISFIED
                ),
                "flags": sorted(flag for flag, value in flags.items() if value),
            },
        )
    )
    await session.commit()

    return _checklist_response(request.action, stored.get(str(request.action)), flags)


@router.get("/compliance", response_model=ComplianceChecklistResponse)
async def read_compliance(
    case_id: uuid.UUID,
    current_user: Annotated[
        User,
        Depends(require_permission(POLICE_INVESTIGATION_OWN, case_id_param="case_id")),
    ],
    action: PoliceAction = PoliceAction.ARREST,
    arrested_person_is_woman: bool | None = None,
    handcuffs_used: bool | None = None,
    memorandum_attested_by_family: bool | None = None,
    bailable_arrest_without_warrant: bool | None = None,
    is_listed_sexual_offence: bool | None = None,
    electronic_device_seized: bool | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> ComplianceChecklistResponse:
    """The checklist for one action, with whatever has been recorded.

    Returns the full checklist even when nothing has been recorded, unlike
    the timeline: the requirements apply whether or not anyone has looked at
    them, and a 404 here would read as "no requirements apply". A flag not
    named in the query comes from the record.
    """
    row = await _row_for(session, case_id)
    stored = (row.compliance_status or {}).get(str(action)) if row else None
    flags = effective_flags(
        row.compliance_flags if row else None,
        {
            "arrested_person_is_woman": arrested_person_is_woman,
            "handcuffs_used": handcuffs_used,
            "memorandum_attested_by_family": memorandum_attested_by_family,
            "bailable_arrest_without_warrant": bailable_arrest_without_warrant,
            "is_listed_sexual_offence": is_listed_sexual_offence,
            "electronic_device_seized": electronic_device_seized,
        },
    )
    return _checklist_response(action, stored, flags)
