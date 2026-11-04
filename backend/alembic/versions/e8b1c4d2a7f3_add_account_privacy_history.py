"""Account recovery, device sessions, consent, erasure receipts, history metadata.

All new tables, each removed with its user by foreign key, so erasure has no
extra step to forget for any of them.

Revision ID: e8b1c4d2a7f3
Revises: d9a4f7c2e610
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e8b1c4d2a7f3"
down_revision: Union[str, Sequence[str], None] = "d9a4f7c2e610"
branch_labels = None
depends_on = None


def _user_fk(**kwargs) -> sa.Column:
    return sa.Column(
        "user_id",
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        **kwargs,
    )


def upgrade() -> None:
    op.create_table(
        "user_security",
        _user_fk(primary_key=True),
        sa.Column("totp_secret_encrypted", sa.Text()),
        sa.Column("totp_confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("totp_last_step", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("must_change_password", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("password_changed_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "mfa_recovery_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        _user_fk(index=True),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "password_reset_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        _user_fk(index=True),
        sa.Column("code_hash", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "issued_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "user_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        _user_fk(),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_user_sessions_user_revoked", "user_sessions", ["user_id", "revoked_at"])
    op.create_table(
        "consent_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        _user_fk(index=True),
        sa.Column("notice_version", sa.String(32), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "erasure_receipts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("erased_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("initiated_by", sa.String(16), nullable=False),
        sa.Column("counts", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
    )
    op.create_table(
        "chat_session_meta",
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        _user_fk(),
        sa.Column("pinned_at", sa.DateTime(timezone=True)),
        sa.Column("matter", sa.String(120)),
    )
    op.create_index("ix_chat_session_meta_user_pinned", "chat_session_meta", ["user_id", "pinned_at"])
    op.create_index("ix_chat_session_meta_user_matter", "chat_session_meta", ["user_id", "matter"])


def downgrade() -> None:
    op.drop_index("ix_chat_session_meta_user_matter", table_name="chat_session_meta")
    op.drop_index("ix_chat_session_meta_user_pinned", table_name="chat_session_meta")
    op.drop_table("chat_session_meta")
    op.drop_table("erasure_receipts")
    op.drop_table("consent_records")
    op.drop_index("ix_user_sessions_user_revoked", table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_table("password_reset_codes")
    op.drop_table("mfa_recovery_codes")
    op.drop_table("user_security")
