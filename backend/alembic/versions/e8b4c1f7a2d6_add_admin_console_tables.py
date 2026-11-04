"""Tables for the administration console, and scrub user text from audit rows.

Sync Deep copied the agent trace into audit metadata, and the retrieval node's
trace holds the question. `case.update` copied case titles and descriptions.
Audit rows outlive the user they name, so those rows are cleaned here as well as
being fixed going forward. There is nothing to restore on downgrade.

Revision ID: e8b4c1f7a2d6
Revises: d9a4f7c2e610
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e8b4c1f7a2d6"
down_revision: Union[str, Sequence[str], None] = "d9a4f7c2e610"
branch_labels = None
depends_on = None

_UUID = postgresql.UUID(as_uuid=True)


def _actor(name: str) -> sa.Column:
    return sa.Column(name, _UUID, sa.ForeignKey("users.id", ondelete="SET NULL"))


def _now(name: str, *, nullable: bool = False) -> sa.Column:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=nullable
    )


def upgrade() -> None:
    op.create_table(
        "release_decisions",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("label", sa.String(64), nullable=False),
        sa.Column("collection", sa.String(128), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("override_failed_gates", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("gate_snapshot", postgresql.JSONB(), nullable=False),
        _actor("decided_by"),
        _now("decided_at"),
        sa.CheckConstraint("decision IN ('approve', 'refuse')", name="decision_valid"),
    )
    op.create_index("ix_release_decisions_label", "release_decisions", ["label"])
    op.create_index("ix_release_decisions_decided_at", "release_decisions", ["decided_at"])

    op.create_table(
        "gate_runs",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("label", sa.String(64), nullable=False),
        sa.Column("collection", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), server_default="queued", nullable=False),
        sa.Column("exit_code", sa.Integer()),
        _actor("requested_by"),
        _now("requested_at"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'passed', 'failed', 'cancelled')",
            name="status_valid",
        ),
    )
    op.create_index("ix_gate_runs_requested_at", "gate_runs", ["requested_at"])
    op.execute(
        "CREATE UNIQUE INDEX uq_gate_runs_one_active ON gate_runs ((1)) "
        "WHERE status IN ('queued', 'running')"
    )

    op.create_table(
        "document_quarantines",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("canonical_document_id", sa.String(128), nullable=False),
        sa.Column("title", sa.String(500)),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("feedback_id", _UUID, sa.ForeignKey("feedback.id", ondelete="SET NULL")),
        _actor("quarantined_by"),
        _now("quarantined_at"),
        sa.Column("released_at", sa.DateTime(timezone=True)),
        _actor("released_by"),
        sa.Column("release_reason", sa.Text()),
    )
    op.create_index(
        "ix_document_quarantines_canonical_document_id",
        "document_quarantines",
        ["canonical_document_id"],
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_document_quarantines_one_active "
        "ON document_quarantines (canonical_document_id) WHERE released_at IS NULL"
    )

    op.create_table(
        "feedback_triage",
        sa.Column(
            "feedback_id",
            _UUID,
            sa.ForeignKey("feedback.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("status", sa.String(16), server_default="open", nullable=False),
        sa.Column("note", sa.Text()),
        _actor("updated_by"),
        _now("updated_at"),
        sa.CheckConstraint(
            "status IN ('open', 'investigating', 'resolved', 'dismissed')", name="status_valid"
        ),
    )

    op.create_table(
        "account_flags",
        sa.Column(
            "user_id", _UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("force_password_reset", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("mfa_required", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("suspended_reason", sa.Text()),
        _actor("updated_by"),
        _now("updated_at"),
    )

    op.create_table(
        "retention_policies",
        sa.Column("category", sa.String(32), primary_key=True),
        sa.Column("days", sa.Integer()),
        _actor("updated_by"),
        _now("updated_at"),
    )

    op.create_table(
        "retention_runs",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column(
            "dry_run_id",
            _UUID,
            sa.ForeignKey("retention_runs.id", ondelete="SET NULL"),
            unique=True,
        ),
        _actor("requested_by"),
        sa.Column("policy", postgresql.JSONB(), nullable=False),
        sa.Column("cutoffs", postgresql.JSONB(), nullable=False),
        sa.Column("counts", postgresql.JSONB(), nullable=False),
        _now("created_at"),
        sa.CheckConstraint("kind IN ('dry_run', 'purge')", name="kind_valid"),
    )
    op.create_index("ix_retention_runs_created_at", "retention_runs", ["created_at"])

    op.create_table(
        "corpus_work_items",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("canonical_document_id", sa.String(128), nullable=False),
        sa.Column("queue", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), server_default="open", nullable=False),
        sa.Column("note", sa.Text()),
        _actor("updated_by"),
        _now("updated_at"),
        sa.UniqueConstraint("canonical_document_id", "queue", name="uq_corpus_work_item"),
        sa.CheckConstraint("queue IN ('ocr', 'verification', 'currency')", name="queue_valid"),
        sa.CheckConstraint("status IN ('open', 'in_progress', 'done')", name="status_valid"),
    )

    op.execute("UPDATE audit_logs SET metadata = metadata - 'agent_trace' WHERE metadata ? 'agent_trace'")
    op.execute(
        "UPDATE audit_logs SET metadata = metadata - 'previous' - 'current' "
        "WHERE action = 'case.update'"
    )


def downgrade() -> None:
    op.drop_table("corpus_work_items")
    op.drop_index("ix_retention_runs_created_at", table_name="retention_runs")
    op.drop_table("retention_runs")
    op.drop_table("retention_policies")
    op.drop_table("account_flags")
    op.drop_table("feedback_triage")
    op.drop_table("document_quarantines")
    op.drop_table("gate_runs")
    op.drop_table("release_decisions")
