"""add citizen deadlines and chat message annotations

C-10 needs somewhere per-user to keep dates. A reopened answer also had no way
to show its section grades or say that it was a safety intervention, because
the message row holds neither.

Revision ID: e3b7c1a94f20
Revises: d9a4f7c2e610
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "e3b7c1a94f20"
down_revision: Union[str, Sequence[str], None] = "d9a4f7c2e610"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "citizen_deadlines",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=False),
        sa.Column("remind_days_before", sa.Integer(), server_default="7", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=32), server_default="manual", nullable=False),
        sa.Column("provision_label", sa.String(length=160), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "remind_days_before >= 0 AND remind_days_before <= 90",
            name="ck_citizen_deadlines_remind_range",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_citizen_deadlines_user_id", "citizen_deadlines", ["user_id"])
    op.create_table(
        "chat_message_annotations",
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("section_confidence", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("safety_kind", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["message_id"], ["chat_messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("message_id"),
    )


def downgrade() -> None:
    op.drop_table("chat_message_annotations")
    op.drop_index("ix_citizen_deadlines_user_id", table_name="citizen_deadlines")
    op.drop_table("citizen_deadlines")
