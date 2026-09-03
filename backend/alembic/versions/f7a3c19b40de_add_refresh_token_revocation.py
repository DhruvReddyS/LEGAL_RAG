"""add refresh token revocation

Refresh tokens were valid for their full lifetime no matter what. Rotation
issued a new pair without invalidating the old one, and logout only cleared a
cookie, which instructs the browser and revokes nothing. A token captured from
a shared machine survived sign-out for its remaining seven days, and an
administrator had no way to end a session.

Revision ID: f7a3c19b40de
Revises: e51c8a2d907f
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "f7a3c19b40de"
down_revision: Union[str, Sequence[str], None] = "e51c8a2d907f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "revoked_refresh_tokens",
        sa.Column("jti", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.String(length=32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_revoked_refresh_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("jti", name=op.f("pk_revoked_refresh_tokens")),
    )
    op.create_index(
        op.f("ix_revoked_refresh_tokens_user_id"),
        "revoked_refresh_tokens",
        ["user_id"],
    )
    # Expired rows are swept on this column; a revoked token that has expired
    # on its own is no longer worth remembering.
    op.create_index(
        "ix_revoked_refresh_tokens_expires_at",
        "revoked_refresh_tokens",
        ["expires_at"],
    )
    # Outstanding tokens cannot be enumerated, so revoking every session for a
    # user works by moving a per-user horizon forward instead.
    op.add_column(
        "users",
        sa.Column("sessions_valid_from", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "sessions_valid_from")
    op.drop_index("ix_revoked_refresh_tokens_expires_at", table_name="revoked_refresh_tokens")
    op.drop_index(op.f("ix_revoked_refresh_tokens_user_id"), table_name="revoked_refresh_tokens")
    op.drop_table("revoked_refresh_tokens")
