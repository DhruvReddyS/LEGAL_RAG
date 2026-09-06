"""Investigation timeline for a police matter.

Deterministic throughout: the handler does date arithmetic against the BNSS
and returns it. There is no model call here, and adding one would defeat
the point -- these dates decide whether a person is lawfully in custody.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.permissions import POLICE_INVESTIGATION_OWN
from app.core.rbac import require_permission
from app.models import AuditLog, User
from app.schemas.investigation import (
    DeadlineResponse,
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
