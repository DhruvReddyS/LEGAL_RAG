from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.permissions import CASE_CREATE, CASE_EDIT_OWN, CASE_READ_OWN
from app.core.rbac import require_permission
from app.models import AuditLog, Case, User
from app.models.enums import CaseRoleType, UserRole
from app.schemas.cases import (
    CaseCreateRequest,
    CaseListResponse,
    CaseResponse,
    CaseStatus,
    CaseUpdateRequest,
)


router = APIRouter(prefix="/cases", tags=["cases"])


def _role_type_for_create(request: CaseCreateRequest, user: User) -> CaseRoleType:
    if user.role in {UserRole.POLICE, UserRole.ADVOCATE}:
        derived = CaseRoleType(user.role.value)
        if request.role_type is not None and request.role_type != derived:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Case role must match the current user role",
            )
        return derived
    if user.role is UserRole.ADMIN and request.role_type is not None:
        return request.role_type
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail="role_type is required when an administrator creates a case",
    )


@router.post("", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
async def create_case(
    request: CaseCreateRequest,
    current_user: Annotated[User, Depends(require_permission(CASE_CREATE))],
    session: AsyncSession = Depends(get_db_session),
) -> Case:
    case = Case(
        owner_id=current_user.id,
        role_type=_role_type_for_create(request, current_user),
        title=request.title,
        status="open",
    )
    session.add(case)
    await session.flush()
    session.add(
        AuditLog(
            user_id=current_user.id,
            action="case.create",
            resource_type="case",
            resource_id=case.id,
            metadata_={"role_type": case.role_type.value, "status": case.status},
        )
    )
    await session.commit()
    await session.refresh(case)
    return case


@router.get("", response_model=CaseListResponse)
async def list_cases(
    current_user: Annotated[
        User, Depends(require_permission(CASE_READ_OWN, infer_case_id=False))
    ],
    case_status: Annotated[CaseStatus | None, Query(alias="status")] = None,
    session: AsyncSession = Depends(get_db_session),
) -> CaseListResponse:
    query = select(Case).where(Case.owner_id == current_user.id)
    if case_status is not None:
        query = query.where(Case.status == case_status)
    cases = list((await session.scalars(query.order_by(Case.created_at.desc()))).all())
    return CaseListResponse(cases=cases, total=len(cases))


@router.get("/{case_id}", response_model=CaseResponse)
async def read_case(
    case_id: uuid.UUID,
    _: Annotated[User, Depends(require_permission(CASE_READ_OWN))],
    session: AsyncSession = Depends(get_db_session),
) -> Case:
    case = await session.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    return case


@router.patch("/{case_id}", response_model=CaseResponse)
async def update_case(
    case_id: uuid.UUID,
    request: CaseUpdateRequest,
    current_user: Annotated[User, Depends(require_permission(CASE_EDIT_OWN))],
    session: AsyncSession = Depends(get_db_session),
) -> Case:
    case = await session.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    changes = request.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="At least one case field must be supplied",
        )
    previous = {field: getattr(case, field) for field in changes}
    for field, value in changes.items():
        setattr(case, field, value)
    session.add(
        AuditLog(
            user_id=current_user.id,
            action="case.update",
            resource_type="case",
            resource_id=case.id,
            metadata_={
                "changed_fields": sorted(changes),
                "previous": previous,
                "current": changes,
            },
        )
    )
    await session.commit()
    await session.refresh(case)
    return case
