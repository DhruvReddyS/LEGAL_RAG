"""Add private per-case notes.

Revision ID: f2a8d6c3b915
Revises: c4f1a7e93b52
Create Date: 2026-11-05

Removing a case or an account removes its notes through the foreign key.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f2a8d6c3b915"
down_revision: Union[str, Sequence[str], None] = "c4f1a7e93b52"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "case_notes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("case_id", sa.UUID(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_case_notes_case_created", "case_notes", ["case_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_case_notes_case_created", table_name="case_notes")
    op.drop_table("case_notes")
