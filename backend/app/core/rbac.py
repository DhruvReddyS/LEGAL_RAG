from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.config import settings
from app.core.security import bearer_scheme, get_optional_current_user
from app.models import Case, Permission, Role, RolePermission, User
from app.models.enums import UserRole


@dataclass(frozen=True)
class PermissionChecker:
    permission_name: str
    case_id_param: str | None = None
    allow_anonymous: bool = False

    async def __call__(
        self,
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
        session: AsyncSession = Depends(get_db_session),
    ) -> User | None:
        current_user = await get_optional_current_user(credentials, session, request=request)
        if current_user is None:
            if self.allow_anonymous and settings.app_env == "development":
                return None
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )

        has_permission = await session.scalar(
            select(Permission.id)
            .join(
                RolePermission,
                RolePermission.permission_id == Permission.id,
            )
            .join(Role, Role.id == RolePermission.role_id)
            .where(
                Role.name == current_user.role.value,
                Permission.name == self.permission_name,
            )
            .limit(1)
        )
        if has_permission is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied",
            )

        if self.case_id_param is not None and current_user.role is not UserRole.ADMIN:
            raw_case_id = request.path_params.get(self.case_id_param)
            if raw_case_id is None:
                raw_case_id = request.query_params.get(self.case_id_param)
            try:
                case_id = uuid.UUID(str(raw_case_id))
            except (TypeError, ValueError) as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"A valid {self.case_id_param} is required",
                ) from exc

            case = await session.get(Case, case_id)
            if case is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Case not found",
                )
            if case.owner_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not own this case",
                )
            if current_user.role in {UserRole.POLICE, UserRole.ADVOCATE}:
                if case.role_type.value != current_user.role.value:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Case role does not match the current user role",
                    )

        return current_user


def require_permission(
    permission_name: str,
    *,
    case_id_param: str | None = None,
    allow_anonymous: bool = False,
    infer_case_id: bool = True,
) -> PermissionChecker:
    resolved_case_id_param = case_id_param
    if (
        infer_case_id
        and
        resolved_case_id_param is None
        and permission_name.endswith(":own")
        and permission_name.startswith(("case:", "police:", "advocate:"))
    ):
        resolved_case_id_param = "case_id"
    return PermissionChecker(
        permission_name=permission_name,
        case_id_param=resolved_case_id_param,
        allow_anonymous=allow_anonymous,
    )
