"""merge role and platform tracks

Revision ID: bad7522c4e64
Revises: e8b1c4d2a7f3, e8b4c1f7a2d6
Create Date: 2026-11-04 22:05:16.873496
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bad7522c4e64'
down_revision: Union[str, Sequence[str], None] = ('e3b7c1a95d20', 'e3b7c1a9f402', 'e8b1c4d2a7f3', 'e8b4c1f7a2d6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
