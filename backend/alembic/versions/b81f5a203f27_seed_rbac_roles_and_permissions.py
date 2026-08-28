"""Seed RBAC roles and permissions.

Revision ID: b81f5a203f27
Revises: 9348c47a69ea
Create Date: 2026-08-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b81f5a203f27"
down_revision: Union[str, Sequence[str], None] = "9348c47a69ea"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ROLE_IDS = {
    "citizen": "00000000-0000-0000-0000-000000000001",
    "police": "00000000-0000-0000-0000-000000000002",
    "advocate": "00000000-0000-0000-0000-000000000003",
    "admin": "00000000-0000-0000-0000-000000000004",
}

PERMISSION_NAMES = (
    "corpus:read",
    "chat:use",
    "bookmark:manage:own",
    "feedback:create",
    "case:create",
    "case:read:own",
    "case:edit:own",
    "case:delete:own",
    "case:document:manage:own",
    "police:investigation:own",
    "advocate:strategy:own",
    "advocate:debate:own",
    "admin:audit:read",
    "admin:user:manage",
    "admin:corpus:manage",
)

PERMISSION_IDS = {
    name: f"00000000-0000-0000-0001-{index:012d}"
    for index, name in enumerate(PERMISSION_NAMES, start=1)
}

ROLE_PERMISSIONS = {
    "citizen": {
        "corpus:read",
        "chat:use",
        "bookmark:manage:own",
        "feedback:create",
    },
    "police": {
        "corpus:read",
        "chat:use",
        "bookmark:manage:own",
        "feedback:create",
        "case:create",
        "case:read:own",
        "case:edit:own",
        "case:delete:own",
        "case:document:manage:own",
        "police:investigation:own",
    },
    "advocate": {
        "corpus:read",
        "chat:use",
        "bookmark:manage:own",
        "feedback:create",
        "case:create",
        "case:read:own",
        "case:edit:own",
        "case:delete:own",
        "case:document:manage:own",
        "advocate:strategy:own",
        "advocate:debate:own",
    },
    "admin": set(PERMISSION_NAMES),
}


def upgrade() -> None:
    roles = sa.table(
        "roles",
        sa.column("id", sa.UUID()),
        sa.column("name", sa.String()),
        sa.column("description", sa.String()),
    )
    permissions = sa.table(
        "permissions",
        sa.column("id", sa.UUID()),
        sa.column("name", sa.String()),
        sa.column("description", sa.String()),
    )
    role_permissions = sa.table(
        "role_permissions",
        sa.column("role_id", sa.UUID()),
        sa.column("permission_id", sa.UUID()),
    )

    op.bulk_insert(
        roles,
        [
            {
                "id": role_id,
                "name": role_name,
                "description": f"Built-in {role_name} role",
            }
            for role_name, role_id in ROLE_IDS.items()
        ],
    )
    op.bulk_insert(
        permissions,
        [
            {
                "id": permission_id,
                "name": permission_name,
                "description": f"Allows {permission_name}",
            }
            for permission_name, permission_id in PERMISSION_IDS.items()
        ],
    )
    op.bulk_insert(
        role_permissions,
        [
            {
                "role_id": ROLE_IDS[role_name],
                "permission_id": PERMISSION_IDS[permission_name],
            }
            for role_name, permission_names in ROLE_PERMISSIONS.items()
            for permission_name in sorted(permission_names)
        ],
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM roles WHERE id = ANY(CAST(:ids AS uuid[]))"),
        {"ids": list(ROLE_IDS.values())},
    )
    bind.execute(
        sa.text("DELETE FROM permissions WHERE id = ANY(CAST(:ids AS uuid[]))"),
        {"ids": list(PERMISSION_IDS.values())},
    )
