"""Check the provisions a draft cites against the codes now in force.

Available to both roles that draft against a matter: an FIR citing IPC
section numbers has the same problem as a petition citing CrPC ones.

No model reads the draft. Citations are extracted by the ingestion
pipeline's own parser and resolved through the official concordance,
because the failure mode of a model here is to confidently renumber a
provision that was actually repealed without replacement.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.permissions import CASE_DOCUMENT_MANAGE_OWN
from app.core.rbac import require_permission
from app.models import AuditLog, User
from app.schemas.authorities import (
    AuthorityCheckRequest,
    AuthorityCheckResponse,
    CitationCheckResponse,
)
from app.services.authority_check import AuthorityFinding, check_authorities

router = APIRouter(prefix="/cases/{case_id}/authorities", tags=["authority-check"])


@router.post("/check", response_model=AuthorityCheckResponse)
async def check_draft_authorities(
    case_id: uuid.UUID,
    request: AuthorityCheckRequest,
    current_user: Annotated[
        User,
        Depends(require_permission(CASE_DOCUMENT_MANAGE_OWN, case_id_param="case_id")),
    ],
    session: AsyncSession = Depends(get_db_session),
) -> AuthorityCheckResponse:
    checks = check_authorities(request.draft)

    session.add(
        AuditLog(
            user_id=current_user.id,
            action="case.authority_check",
            resource_type="case",
            resource_id=case_id,
            metadata_={
                "citations": len(checks),
                # The draft itself is never recorded. It is privileged work
                # product, and the audit log answers "who checked what, when",
                # not "what did their petition say".
                "needs_attention": [c.citation for c in checks if c.needs_attention],
            },
        )
    )
    await session.commit()

    return AuthorityCheckResponse(
        checked=[
            CitationCheckResponse(
                citation=c.citation,
                code=c.code,
                section=c.section,
                finding=c.finding,
                successors=list(c.successors),
                advice=c.advice,
                needs_attention=c.needs_attention,
            )
            for c in checks
        ],
        needs_attention=sum(c.needs_attention for c in checks),
        not_re_enacted=sum(
            c.finding is AuthorityFinding.NOT_RE_ENACTED for c in checks
        ),
        not_checked=sum(c.finding is AuthorityFinding.NOT_CHECKED for c in checks),
    )
