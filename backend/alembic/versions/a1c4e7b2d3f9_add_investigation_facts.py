"""Add recorded dates for a police investigation.

Revision ID: a1c4e7b2d3f9
Revises: f7a3c19b40de
Create Date: 2026-09-06

Its own table rather than columns on `cases`. A case is either a police
matter or an advocate's brief, and a brief has no arrest time, no remand
date and no inquest -- seven nullable columns on the shared table would be
null for half the rows and would invite reading a null as a fact.

`gravity` defaults to 'unknown' rather than to a period. That is the whole
point of the column: "we did not record this" has to survive a round trip
through the database as itself. A default of 'other' would silently give
every unrecorded offence a sixty-day s.187(3) deadline, which is the
assumption that hides a default-bail entitlement.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "a1c4e7b2d3f9"
down_revision: Union[str, Sequence[str], None] = "f7a3c19b40de"
branch_labels = None
depends_on = None


# create_type=False, or create_table emits a second CREATE TYPE for the same
# enum and the migration dies on DuplicateObjectError. The type is created
# once, explicitly, in upgrade().
offence_gravity = postgresql.ENUM(
    "death_life_or_ten_years_or_more",
    "other",
    "unknown",
    name="offence_gravity",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    offence_gravity.create(bind, checkfirst=True)

    op.create_table(
        "investigation_facts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("case_id", sa.UUID(), nullable=False),
        sa.Column("information_recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("arrested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_remand_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accused_produced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("death_occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "preliminary_enquiry_started_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "gravity",
            offence_gravity,
            server_default="unknown",
            nullable=False,
        ),
        sa.Column(
            "is_listed_sexual_offence",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "is_unnatural_death",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # One row per case. Two rows would mean two answers to "when was the
        # accused first remanded", and the deadline arithmetic would silently
        # use whichever came back first.
        sa.UniqueConstraint("case_id", name="uq_investigation_facts_case_id"),
    )
    op.create_index(
        "ix_investigation_facts_case_id", "investigation_facts", ["case_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_investigation_facts_case_id", table_name="investigation_facts")
    op.drop_table("investigation_facts")
    offence_gravity.drop(op.get_bind(), checkfirst=True)
