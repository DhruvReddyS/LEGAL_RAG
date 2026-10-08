"""Order chat messages by insert order instead of a shared timestamp.

Revision ID: c7e2a9b41d08
Revises: b2d5f8c1e4a7
Create Date: 2026-10-08

`chat_messages.created_at` defaults to `now()`, which in PostgreSQL is the
*transaction* timestamp. A chat request writes the user's question and the
assistant's answer in one transaction, so both rows carry a byte-identical
timestamp and `ORDER BY created_at` leaves the winner to the planner.

Measured before this migration: 1,225 of 2,912 stored messages share a
timestamp with a sibling in the same session. A citizen reading their own
history could be shown the answer above the question, and
`test_chat_persistence_and_session_ownership` failed roughly one run in three
for exactly this reason.

The session-list query had already hit it and worked around it in place, with
a comment and an explicit role tiebreak -- correct there, and not a property
anything else could rely on. A monotonic column makes insert order a fact of
the row rather than a rule each query has to remember, and the workaround can
go.

A sequence, not a finer clock. `clock_timestamp()` would also separate the two
rows and would still be a timestamp: two inserts in the same microsecond stay
ambiguous, and nothing stops a later migration putting `now()` back. A
monotonic integer cannot tie.

Backfill order within a collision is (user, then assistant), because an
assistant message answers the question above it. Outside a collision the
timestamp decides, so existing conversations keep the order they were read in.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c7e2a9b41d08"
down_revision: Union[str, Sequence[str], None] = "b2d5f8c1e4a7"
branch_labels = None
depends_on = None


SEQUENCE_NAME = "chat_messages_sequence_seq"


def upgrade() -> None:
    op.execute(sa.text(f"CREATE SEQUENCE IF NOT EXISTS {SEQUENCE_NAME}"))
    op.add_column("chat_messages", sa.Column("sequence", sa.BigInteger(), nullable=True))
    # Existing rows first, so the column can be made NOT NULL. Ordered by the
    # timestamp, then the question before its answer, then the id so the
    # result is deterministic even for a three-way tie.
    op.execute(
        sa.text(
            """
            UPDATE chat_messages AS target
            SET sequence = ordered.position
            FROM (
                SELECT
                    id,
                    row_number() OVER (
                        ORDER BY
                            created_at,
                            CASE role WHEN 'user' THEN 0 WHEN 'assistant' THEN 1 ELSE 2 END,
                            id
                    ) AS position
                FROM chat_messages
            ) AS ordered
            WHERE target.id = ordered.id
            """
        )
    )
    # Past every backfilled value, so the first new message cannot collide
    # with history.
    op.execute(
        sa.text(
            f"SELECT setval('{SEQUENCE_NAME}', "
            "COALESCE((SELECT MAX(sequence) FROM chat_messages), 0) + 1, false)"
        )
    )
    op.alter_column(
        "chat_messages",
        "sequence",
        nullable=False,
        server_default=sa.text(f"nextval('{SEQUENCE_NAME}')"),
    )
    op.execute(sa.text(f"ALTER SEQUENCE {SEQUENCE_NAME} OWNED BY chat_messages.sequence"))
    # Every read of a conversation is "this session, in order".
    op.create_index(
        "ix_chat_messages_session_id_sequence",
        "chat_messages",
        ["session_id", "sequence"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_chat_messages_session_id_sequence", table_name="chat_messages")
    # The column owns the sequence, so dropping it drops the sequence too.
    op.drop_column("chat_messages", "sequence")
    op.execute(sa.text(f"DROP SEQUENCE IF EXISTS {SEQUENCE_NAME}"))
