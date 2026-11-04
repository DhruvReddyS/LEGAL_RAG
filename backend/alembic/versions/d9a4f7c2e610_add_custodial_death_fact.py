"""Record whether a death occurred in custody.

The 24-hour duty to forward the body is BNSS s.196(6), and it attaches to an
inquiry under s.196(2): a death or disappearance in custody. It was being applied
to every unnatural death, citing a sub-section s.194 does not have.

Revision ID: d9a4f7c2e610
Revises: c7e2a9b41d08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d9a4f7c2e610"
down_revision: Union[str, Sequence[str], None] = "c7e2a9b41d08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "investigation_facts",
        sa.Column("is_custodial_death", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("investigation_facts", "is_custodial_death")
