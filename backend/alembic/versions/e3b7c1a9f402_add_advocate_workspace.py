"""Add the advocate workspace: saved work products, matter calendar, debate jobs.

Revision ID: e3b7c1a9f402
Revises: d9a4f7c2e610
Create Date: 2026-11-04

`documents_generated` is deliberately not reused. Its list endpoint and the
workspace read every row as an FIR draft, so advocate work products filed
there would surface as blank drafts.

The enum value cannot be removed on downgrade: PostgreSQL has no DROP VALUE.
It is harmless left behind, since nothing can enqueue it without this code.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "e3b7c1a9f402"
down_revision: Union[str, Sequence[str], None] = "d9a4f7c2e610"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'debate_room'")

    op.create_table(
        "advocate_work_products",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("case_id", sa.UUID(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_id", "kind", "version", name="uq_advocate_work_case_kind_version"),
    )
    op.create_index(
        "ix_advocate_work_case_created", "advocate_work_products", ["case_id", "created_at"]
    )

    op.create_table(
        "matter_calendar_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("case_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("basis", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_matter_calendar_case_due", "matter_calendar_events", ["case_id", "due_on"])


def downgrade() -> None:
    op.drop_index("ix_matter_calendar_case_due", table_name="matter_calendar_events")
    op.drop_table("matter_calendar_events")
    op.drop_index("ix_advocate_work_case_created", table_name="advocate_work_products")
    op.drop_table("advocate_work_products")
