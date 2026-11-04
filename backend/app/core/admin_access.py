"""The read trail for an administrator reaching someone else's material.

The architecture document justifies administrative access to a named matter by
saying that naming it is what makes it authorised and auditable. Reads wrote no
row, so an administrator could read a conversation, download evidence and open a
draft and `audit_logs` showed nothing. This is the one place that row is written.

The row names the resource and whose it is. It never carries what the resource
says: an audit row must not become a second copy of a disclosure.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, User


async def record_admin_access(
    session: AsyncSession,
    admin: User,
    *,
    action: str,
    resource_type: str,
    resource_id: uuid.UUID | None,
    owner_id: uuid.UUID | None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Commit a durable row before the material is returned.

    Committed here rather than left for the handler, because read handlers do
    not commit: a row added and never flushed is exactly the missing trail this
    exists to fix.
    """
    session.add(
        AuditLog(
            user_id=admin.id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata_={
                "owner_id": str(owner_id) if owner_id else None,
                **(metadata or {}),
            },
        )
    )
    await session.commit()
