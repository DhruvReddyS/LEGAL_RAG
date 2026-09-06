"""Record which BNSS requirements have been confirmed for a matter.

Revision ID: b2d5f8c1e4a7
Revises: a1c4e7b2d3f9
Create Date: 2026-09-06

A JSONB map of requirement key to status, on the row that already holds the
investigation's dates. Its own table would buy nothing: the rows are keyed
by the same case, written together, and read together.

Nullable with no server default, because an absent map and an empty map
mean the same thing here -- nothing has been confirmed -- and the service
treats every unlisted key as NOT_RECORDED. There is deliberately no way to
express "satisfied" by omission.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b2d5f8c1e4a7"
down_revision: Union[str, Sequence[str], None] = "a1c4e7b2d3f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "investigation_facts",
        sa.Column(
            "compliance_status",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("investigation_facts", "compliance_status")
