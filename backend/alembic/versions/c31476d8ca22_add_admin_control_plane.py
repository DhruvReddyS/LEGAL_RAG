"""Add admin user lifecycle and governed corpus intake.

Revision ID: c31476d8ca22
Revises: 715f5f1309e4
Create Date: 2026-08-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "c31476d8ca22"
down_revision: Union[str, Sequence[str], None] = "715f5f1309e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.create_index("ix_users_is_active", "users", ["is_active"])
    op.create_table(
        "corpus_intakes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("storage_object_id", sa.UUID(), nullable=False),
        sa.Column("corpus_source_id", sa.UUID(), nullable=True),
        sa.Column("uploaded_by", sa.UUID(), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column(
            "source_type",
            postgresql.ENUM("act", "judgment", "notification", name="corpus_source_type", create_type=False),
            nullable=False,
        ),
        sa.Column("jurisdiction", sa.String(length=255), nullable=False),
        sa.Column("authority", sa.String(length=255), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="staged", nullable=False),
        sa.Column("validation_summary", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["corpus_source_id"], ["corpus_sources.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["storage_object_id"], ["storage_objects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_object_id"),
    )
    op.create_index("ix_corpus_intakes_status", "corpus_intakes", ["status"])
    op.create_index("ix_corpus_intakes_uploaded_by", "corpus_intakes", ["uploaded_by"])


def downgrade() -> None:
    op.drop_index("ix_corpus_intakes_uploaded_by", table_name="corpus_intakes")
    op.drop_index("ix_corpus_intakes_status", table_name="corpus_intakes")
    op.drop_table("corpus_intakes")
    op.drop_index("ix_users_is_active", table_name="users")
    op.drop_column("users", "is_active")
