"""Add corpus lifecycle tables: currency state, law-change notices, finding reviews, expert review.

Revision ID: c4f1a7e93b52
Revises: bad7522c4e64
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c4f1a7e93b52"
down_revision: Union[str, Sequence[str], None] = "bad7522c4e64"
branch_labels = None
depends_on = None

_UUID = postgresql.UUID(as_uuid=True)


def _actor(name: str) -> sa.Column:
    return sa.Column(name, _UUID, sa.ForeignKey("users.id", ondelete="SET NULL"))


def _now(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    op.create_table(
        "document_currency_states",
        sa.Column("canonical_document_id", sa.String(128), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("superseded_by", sa.String(500)),
        _now("recorded_at"),
    )

    op.create_table(
        "law_change_notices",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("user_id", _UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "message_id", _UUID, sa.ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("canonical_document_id", sa.String(128), nullable=False),
        sa.Column("document_title", sa.String(500), nullable=False),
        sa.Column("previous_status", sa.String(16), nullable=False),
        sa.Column("current_status", sa.String(16), nullable=False),
        sa.Column("superseded_by", sa.String(500)),
        sa.Column("effective", sa.String(32)),
        sa.Column("basis", sa.Text()),
        sa.Column("change_key", sa.String(64), nullable=False),
        _now("created_at"),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("message_id", "change_key", name="uq_law_change_notice_message_change"),
    )
    op.create_index("ix_law_change_notices_user_read", "law_change_notices", ["user_id", "read_at"])
    op.create_index("ix_law_change_notices_message_id", "law_change_notices", ["message_id"])

    op.create_table(
        "amendment_finding_reviews",
        sa.Column("finding_id", sa.String(64), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("note", sa.Text()),
        _actor("reviewed_by"),
        _now("reviewed_at"),
        sa.CheckConstraint("status IN ('open', 'reviewed', 'dismissed')", name="status_valid"),
    )

    op.create_table(
        "expert_review_items",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column(
            "message_id",
            _UUID,
            sa.ForeignKey("chat_messages.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("answered_month", sa.String(7), nullable=False),
        sa.Column("citations", postgresql.JSONB(), nullable=False),
        _actor("sampled_by"),
        _now("sampled_at"),
    )
    op.create_index("ix_expert_review_items_sampled_at", "expert_review_items", ["sampled_at"])

    op.create_table(
        "expert_review_claims",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column(
            "item_id", _UUID, sa.ForeignKey("expert_review_items.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("verdict", sa.String(16)),
        sa.Column("note", sa.Text()),
        _actor("reviewed_by"),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("item_id", "ordinal", name="uq_expert_review_claim_ordinal"),
        sa.CheckConstraint(
            "verdict IS NULL OR verdict IN ('correct', 'incorrect', 'unsure')", name="verdict_valid"
        ),
    )
    op.create_index("ix_expert_review_claims_item_id", "expert_review_claims", ["item_id"])


def downgrade() -> None:
    op.drop_table("expert_review_claims")
    op.drop_table("expert_review_items")
    op.drop_table("amendment_finding_reviews")
    op.drop_table("law_change_notices")
    op.drop_table("document_currency_states")
