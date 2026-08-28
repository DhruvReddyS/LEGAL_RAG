from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.permissions import CORPUS_READ
from app.core.rbac import require_permission
from app.ingestion.init_qdrant import ADVOCATE_CASE_DATA, POLICE_CASE_DATA
from app.models import Case, User
from app.models.enums import CaseRoleType, UserRole


SearchMode = Literal["general", "case_specific"]


@dataclass(frozen=True)
class AuthorizedCaseScope:
    mode: SearchMode
    case_ids_by_role: dict[CaseRoleType, list[uuid.UUID]]


async def resolve_authorized_case_scope(
    mode: Annotated[SearchMode, Query()] = "general",
    case_id: Annotated[uuid.UUID | None, Query()] = None,
    current_user: User = Depends(require_permission(CORPUS_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> AuthorizedCaseScope:
    if mode == "case_specific" and case_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="case_id is required for case_specific search",
        )
    if mode == "general" and case_id is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="case_id is only valid for case_specific search",
        )

    query = select(Case)
    if mode == "case_specific":
        query = query.where(Case.id == case_id)
    if current_user.role is not UserRole.ADMIN:
        query = query.where(Case.owner_id == current_user.id)
    cases = list((await session.scalars(query)).all())

    if mode == "case_specific" and not cases:
        # Do not disclose whether another user's private case exists.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    grouped = {CaseRoleType.POLICE: [], CaseRoleType.ADVOCATE: []}
    for case in cases:
        if current_user.role in {UserRole.POLICE, UserRole.ADVOCATE}:
            if case.role_type.value != current_user.role.value:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Case role does not match the current user role",
                )
        grouped[case.role_type].append(case.id)
    return AuthorizedCaseScope(mode=mode, case_ids_by_role=grouped)


def collection_for_case_role(role: CaseRoleType) -> str:
    return POLICE_CASE_DATA if role is CaseRoleType.POLICE else ADVOCATE_CASE_DATA
