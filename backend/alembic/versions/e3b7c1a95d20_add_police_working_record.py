"""Add the police working record and the supervisor permission.

Evidence, custody, witnesses, searches, offence assessments, remand periods and the
case diary get tables of their own. The facts table gains what POL-5 and POL-8 need
(rape as distinct from the s.193(2) listing, the arrest type, the report date) and the
compliance flags, which decide which conditional rows are listed and so have to
survive a reload.

The supervisor permission is granted to the police role but does nothing alone: a
view also needs an explicit supervisor row in police_unit_members, which only an
administrator can write.

Revision ID: e3b7c1a95d20
Revises: d9a4f7c2e610
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e3b7c1a95d20"
down_revision: Union[str, Sequence[str], None] = "d9a4f7c2e610"
branch_labels = None
depends_on = None

POLICE_ROLE_ID = "00000000-0000-0000-0000-000000000002"
PERMISSION_ID = "5f1c0e6a-7d9b-4a56-9e8c-2d1b7c3a9f01"
PERMISSION_NAME = "police:unit:supervise"


def _id() -> sa.Column:
    return sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True)


def _case() -> sa.Column:
    return sa.Column(
        "case_id",
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


def _user(name: str = "recorded_by") -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"))


def _at(name: str, nullable: bool = True) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def _created(name: str = "created_at") -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    op.add_column(
        "investigation_facts",
        sa.Column("is_rape_or_attempt", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column("investigation_facts", _at("victim_examined_at"))
    op.add_column("investigation_facts", sa.Column("arrested_under_warrant", sa.Boolean()))
    op.add_column("investigation_facts", _at("police_report_forwarded_at"))
    op.add_column(
        "investigation_facts",
        sa.Column("special_statute", sa.String(30), server_default="none", nullable=False),
    )
    op.add_column("investigation_facts", sa.Column("compliance_flags", postgresql.JSONB()))

    # The s.184 deadline used to fire on the listing flag. Nothing recorded says which
    # of the listed offences a row concerns, so it is not carried over: an officer
    # with a rape case states it once, rather than every listed case being told to
    # send "the woman" for examination.

    op.create_table(
        "police_searches",
        _id(),
        _case(),
        sa.Column("place", sa.Text(), nullable=False),
        sa.Column("basis", sa.String(20), server_default="unknown", nullable=False),
        _at("searched_at"),
        _at("grounds_recorded_at"),
        _at("record_sent_to_magistrate_at"),
        _at("recording_forwarded_at"),
        sa.Column("witness_count", sa.Integer()),
        sa.Column("answers", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("notes", sa.Text()),
        _user(),
        _created(),
        _created("updated_at"),
    )
    op.create_table(
        "police_evidence_items",
        _id(),
        _case(),
        sa.Column("exhibit_label", sa.String(60), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(20), server_default="physical", nullable=False),
        _at("seized_at"),
        sa.Column("seized_from", sa.Text()),
        sa.Column("seized_by", sa.String(255)),
        sa.Column(
            "search_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("police_searches.id", ondelete="SET NULL"),
        ),
        sa.Column("status", sa.String(30), server_default="held", nullable=False),
        sa.Column("storage_location", sa.Text()),
        sa.Column("digital_hash", sa.String(255)),
        sa.Column("certificate_s63", sa.String(10), server_default="unknown", nullable=False),
        _at("reported_to_magistrate_at"),
        sa.Column("notes", sa.Text()),
        _user(),
        _created(),
        _created("updated_at"),
        sa.UniqueConstraint("case_id", "exhibit_label", name="uq_police_exhibit_label"),
    )
    op.create_table(
        "police_custody_events",
        _id(),
        _case(),
        sa.Column(
            "evidence_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("police_evidence_items.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        _at("occurred_at", nullable=False),
        sa.Column("from_person", sa.String(255), nullable=False),
        sa.Column("to_person", sa.String(255), nullable=False),
        sa.Column("purpose", sa.Text()),
        sa.Column("place", sa.Text()),
        sa.Column(
            "corrects_event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("police_custody_events.id", ondelete="SET NULL"),
        ),
        _user(),
        _created(),
    )
    op.create_table(
        "police_witnesses",
        _id(),
        _case(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(30), server_default="other", nullable=False),
        sa.Column("contact", sa.Text()),
        sa.Column("attends_only_at_residence", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("needs_woman_officer", sa.Boolean(), server_default="false", nullable=False),
        _at("statement_recorded_at"),
        sa.Column("statement_mode", sa.String(20)),
        sa.Column("recorded_by_woman_officer", sa.String(10), server_default="unknown", nullable=False),
        sa.Column("inserted_in_diary", sa.String(10), server_default="unknown", nullable=False),
        _at("magistrate_statement_at"),
        _at("bond_executed_at"),
        sa.Column("status", sa.String(30), server_default="to_be_examined", nullable=False),
        sa.Column("notes", sa.Text()),
        _user(),
        _created(),
        _created("updated_at"),
    )
    op.create_table(
        "police_deadline_completions",
        _id(),
        _case(),
        sa.Column("deadline_key", sa.String(120), nullable=False),
        _at("completed_at", nullable=False),
        sa.Column("note", sa.Text()),
        _user(),
        _created(),
        sa.UniqueConstraint("case_id", "deadline_key", name="uq_police_deadline_done"),
    )
    op.create_table(
        "police_compliance_records",
        _id(),
        _case(),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("requirement_key", sa.String(80), nullable=False),
        _at("occurred_at"),
        sa.Column("evidence_note", sa.Text()),
        sa.Column(
            "evidence_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("police_evidence_items.id", ondelete="SET NULL"),
        ),
        _user(),
        _created("updated_at"),
        sa.UniqueConstraint("case_id", "action", "requirement_key", name="uq_police_compliance_record"),
    )
    op.create_table(
        "police_offence_assessments",
        _id(),
        _case(),
        sa.Column("offence_key", sa.String(60), nullable=False),
        sa.Column("elements", postgresql.JSONB(), server_default="{}", nullable=False),
        _user(),
        _created("updated_at"),
        sa.UniqueConstraint("case_id", "offence_key", name="uq_police_offence_assessment"),
    )
    op.create_table(
        "police_remand_periods",
        _id(),
        _case(),
        sa.Column("custody_type", sa.String(10), nullable=False),
        sa.Column("from_date", sa.Date(), nullable=False),
        sa.Column("to_date", sa.Date(), nullable=False),
        sa.Column("magistrate", sa.String(255)),
        sa.Column("order_reference", sa.String(255)),
        _user(),
        _created(),
    )
    op.create_table(
        "police_diary_entries",
        _id(),
        _case(),
        sa.Column("page_no", sa.Integer(), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        _at("information_reached_at"),
        _at("began_at"),
        _at("closed_at"),
        sa.Column("places_visited", sa.Text()),
        sa.Column("circumstances", sa.Text(), nullable=False),
        sa.Column("statements_inserted", sa.Text()),
        sa.Column("corrects_page", sa.Integer()),
        _user(),
        _created(),
        sa.UniqueConstraint("case_id", "page_no", name="uq_police_diary_page"),
    )
    op.create_table(
        "police_units",
        _id(),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        _user("created_by"),
        _created(),
    )
    op.create_table(
        "police_unit_members",
        _id(),
        sa.Column(
            "unit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("police_units.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("role", sa.String(12), server_default="member", nullable=False),
        _user("added_by"),
        _created("added_at"),
        sa.UniqueConstraint("unit_id", "user_id", name="uq_police_unit_member"),
    )

    bind = op.get_bind()
    bind.execute(
        sa.text(
            "INSERT INTO permissions (id, name, description) "
            "VALUES (CAST(:id AS uuid), :name, :description)"
        ),
        {
            "id": PERMISSION_ID,
            "name": PERMISSION_NAME,
            "description": "May hold a supervisor grant over a police unit",
        },
    )
    bind.execute(
        sa.text(
            "INSERT INTO role_permissions (role_id, permission_id) "
            "VALUES (CAST(:role AS uuid), CAST(:permission AS uuid))"
        ),
        {"role": POLICE_ROLE_ID, "permission": PERMISSION_ID},
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM role_permissions WHERE permission_id = CAST(:p AS uuid)"),
        {"p": PERMISSION_ID},
    )
    bind.execute(sa.text("DELETE FROM permissions WHERE id = CAST(:p AS uuid)"), {"p": PERMISSION_ID})
    for table in (
        "police_unit_members",
        "police_units",
        "police_diary_entries",
        "police_remand_periods",
        "police_offence_assessments",
        "police_compliance_records",
        "police_deadline_completions",
        "police_witnesses",
        "police_custody_events",
        "police_evidence_items",
        "police_searches",
    ):
        op.drop_table(table)
    for column in (
        "compliance_flags",
        "special_statute",
        "police_report_forwarded_at",
        "arrested_under_warrant",
        "victim_examined_at",
        "is_rape_or_attempt",
    ):
        op.drop_column("investigation_facts", column)
