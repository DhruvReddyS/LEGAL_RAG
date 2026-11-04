"""Full user management, citizens included.

Administrator accounts are not managed from here. There is no route that creates
one, and one administrator suspending or demoting another is the shortest path to
locking everyone out. Those changes stay a deliberate database operation.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Case, User
from app.models.admin_tools import AccountFlag
from app.models.enums import UserRole


async def account_flags_for(session: AsyncSession, user_id: uuid.UUID) -> AccountFlag | None:
    """What sign-in checks. Absent means no requirement has ever been set."""
    return await session.get(AccountFlag, user_id)


async def list_users(
    session: AsyncSession,
    *,
    q: str,
    role: str | None,
    status: str | None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    filters = []
    needle = q.strip()
    if needle:
        pattern = "%" + needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        filters.append(or_(User.name.ilike(pattern, escape="\\"), User.email.ilike(pattern, escape="\\")))
    if role:
        filters.append(User.role == UserRole(role))
    if status == "active":
        filters.append(User.is_active.is_(True))
    elif status == "suspended":
        filters.append(User.is_active.is_(False))

    total = int(await session.scalar(select(func.count(User.id)).where(*filters)) or 0)
    case_counts = (
        select(Case.owner_id, func.count(Case.id).label("cases")).group_by(Case.owner_id).subquery()
    )
    last_login = (
        select(AuditLog.user_id, func.max(AuditLog.timestamp).label("at"))
        .where(AuditLog.action == "auth.login")
        .group_by(AuditLog.user_id)
        .subquery()
    )
    rows = (
        await session.execute(
            select(User, func.coalesce(case_counts.c.cases, 0), last_login.c.at, AccountFlag)
            .outerjoin(case_counts, case_counts.c.owner_id == User.id)
            .outerjoin(last_login, last_login.c.user_id == User.id)
            .outerjoin(AccountFlag, AccountFlag.user_id == User.id)
            .where(*filters)
            .order_by(User.created_at.desc(), User.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    role_rows = (await session.execute(select(User.role, func.count(User.id)).group_by(User.role))).all()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "by_role": {row[0].value: int(row[1]) for row in role_rows},
        "users": [_user(user, int(cases), login, flag) for user, cases, login, flag in rows],
    }


def _user(user: User, cases: int, last_login: datetime | None, flag: AccountFlag | None) -> dict[str, Any]:
    return {
        "id": str(user.id),
        "name": user.name,
        "email": user.email,
        "role": user.role.value,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat(),
        "case_count": cases,
        "last_login_at": last_login.isoformat() if last_login else None,
        "sessions_valid_from": user.sessions_valid_from.isoformat() if user.sessions_valid_from else None,
        "force_password_reset": bool(flag and flag.force_password_reset),
        "mfa_required": bool(flag and flag.mfa_required),
        "suspended_reason": flag.suspended_reason if flag else None,
        "manageable": user.role is not UserRole.ADMIN,
    }


async def _manageable(session: AsyncSession, user_id: uuid.UUID, admin: User) -> User:
    target = await session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == admin.id:
        raise HTTPException(status_code=409, detail="An administrator cannot change their own account here")
    if target.role is UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Administrator accounts are not managed here")
    return target


async def _flag(session: AsyncSession, user_id: uuid.UUID) -> AccountFlag:
    flag = await session.get(AccountFlag, user_id)
    if flag is None:
        flag = AccountFlag(user_id=user_id)
        session.add(flag)
    return flag


async def _finish(
    session: AsyncSession, target: User, admin: User, action: str, metadata: dict[str, Any]
) -> dict[str, Any]:
    session.add(
        AuditLog(
            user_id=admin.id,
            action=action,
            resource_type="user",
            resource_id=target.id,
            metadata_=metadata,
        )
    )
    await session.commit()
    await session.refresh(target)
    flag = await session.get(AccountFlag, target.id)
    cases = int(await session.scalar(select(func.count(Case.id)).where(Case.owner_id == target.id)) or 0)
    return _user(target, cases, None, flag)


def _end_sessions(target: User) -> None:
    # Checked on every request and every refresh, so this takes effect at once.
    target.sessions_valid_from = datetime.now(timezone.utc)


async def suspend_user(session: AsyncSession, *, admin: User, user_id: uuid.UUID, reason: str) -> dict[str, Any]:
    target = await _manageable(session, user_id, admin)
    target.is_active = False
    _end_sessions(target)
    flag = await _flag(session, target.id)
    flag.suspended_reason = reason
    flag.updated_by = admin.id
    return await _finish(session, target, admin, "admin.user.suspend", {"has_reason": True})


async def reactivate_user(session: AsyncSession, *, admin: User, user_id: uuid.UUID) -> dict[str, Any]:
    target = await _manageable(session, user_id, admin)
    target.is_active = True
    flag = await _flag(session, target.id)
    flag.suspended_reason = None
    flag.updated_by = admin.id
    return await _finish(session, target, admin, "admin.user.reactivate", {})


async def revoke_sessions(session: AsyncSession, *, admin: User, user_id: uuid.UUID) -> dict[str, Any]:
    target = await _manageable(session, user_id, admin)
    _end_sessions(target)
    return await _finish(session, target, admin, "admin.user.revoke_sessions", {})


async def force_password_reset(
    session: AsyncSession, *, admin: User, user_id: uuid.UUID, required: bool
) -> dict[str, Any]:
    target = await _manageable(session, user_id, admin)
    flag = await _flag(session, target.id)
    flag.force_password_reset = required
    flag.updated_by = admin.id
    if required:
        _end_sessions(target)
    return await _finish(session, target, admin, "admin.user.force_password_reset", {"required": required})


async def set_mfa_required(
    session: AsyncSession, *, admin: User, user_id: uuid.UUID, required: bool
) -> dict[str, Any]:
    target = await _manageable(session, user_id, admin)
    flag = await _flag(session, target.id)
    flag.mfa_required = required
    flag.updated_by = admin.id
    return await _finish(session, target, admin, "admin.user.mfa_required", {"required": required})


async def change_role(
    session: AsyncSession, *, admin: User, user_id: uuid.UUID, role: UserRole
) -> dict[str, Any]:
    target = await _manageable(session, user_id, admin)
    if role is UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Administrator access cannot be granted here")
    if role is target.role:
        raise HTTPException(status_code=409, detail="The account already has this role")
    cases = int(await session.scalar(select(func.count(Case.id)).where(Case.owner_id == target.id)) or 0)
    if cases:
        # A case belongs to a role's private collection. Moving the owner would
        # strand their evidence behind a role check they no longer pass.
        raise HTTPException(status_code=409, detail="Role cannot change while the account owns cases")
    before = target.role.value
    target.role = role
    # A token carries the role and is refused once it no longer matches, but the
    # refresh token would otherwise mint a new one.
    _end_sessions(target)
    return await _finish(
        session, target, admin, "admin.user.role_change", {"before": before, "after": role.value}
    )
