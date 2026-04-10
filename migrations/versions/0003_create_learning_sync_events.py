"""create learning sync events table

Revision ID: 0003_create_learning_sync_events
Revises: 0581b5617aea
Create Date: 2026-04-10 08:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0003_create_learning_sync_events"
down_revision: Union[str, None] = "0581b5617aea"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "learning_sync_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("client_session_id", sa.UUID(), nullable=False),
        sa.Column("topic_id", sa.UUID(), nullable=False),
        sa.Column("learning_session_id", sa.UUID(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["learning_session_id"], ["learning_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_session_id"),
    )
    op.create_index(op.f("ix_learning_sync_events_user_id"), "learning_sync_events", ["user_id"], unique=False)
    op.create_index(op.f("ix_learning_sync_events_client_session_id"), "learning_sync_events", ["client_session_id"], unique=True)
    op.create_index(op.f("ix_learning_sync_events_topic_id"), "learning_sync_events", ["topic_id"], unique=False)
    op.create_index(op.f("ix_learning_sync_events_learning_session_id"), "learning_sync_events", ["learning_session_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_learning_sync_events_learning_session_id"), table_name="learning_sync_events")
    op.drop_index(op.f("ix_learning_sync_events_topic_id"), table_name="learning_sync_events")
    op.drop_index(op.f("ix_learning_sync_events_client_session_id"), table_name="learning_sync_events")
    op.drop_index(op.f("ix_learning_sync_events_user_id"), table_name="learning_sync_events")
    op.drop_table("learning_sync_events")
