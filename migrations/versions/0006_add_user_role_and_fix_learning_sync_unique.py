"""add user role and fix learning sync unique drift

Revision ID: 0006_user_role_fix_sync
Revises: c1b9d88b5614
Create Date: 2026-04-19 23:59:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "0006_user_role_fix_sync"
down_revision: Union[str, None] = "c1b9d88b5614"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


user_role_enum = postgresql.ENUM(
    "user",
    "admin",
    name="userrole",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    user_role_enum.create(bind, checkfirst=True)

    user_columns = {column["name"] for column in inspector.get_columns("users")}
    if "role" not in user_columns:
        op.add_column(
            "users",
            sa.Column(
                "role",
                user_role_enum,
                nullable=False,
                server_default="user",
            ),
        )

    op.execute("UPDATE users SET role = 'user' WHERE role IS NULL")
    op.alter_column("users", "role", server_default=None)

    op.execute(
        """
        DO $$
        DECLARE
            idx_is_unique BOOLEAN;
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'learning_sync_events_client_session_id_key'
                  AND conrelid = 'learning_sync_events'::regclass
            ) THEN
                SELECT i.indisunique INTO idx_is_unique
                FROM pg_class c
                JOIN pg_index i ON i.indexrelid = c.oid
                JOIN pg_class t ON t.oid = i.indrelid
                WHERE c.relname = 'ix_learning_sync_events_client_session_id'
                  AND t.relname = 'learning_sync_events'
                LIMIT 1;

                IF idx_is_unique THEN
                    ALTER TABLE learning_sync_events
                    ADD CONSTRAINT learning_sync_events_client_session_id_key
                    UNIQUE USING INDEX ix_learning_sync_events_client_session_id;
                ELSE
                    ALTER TABLE learning_sync_events
                    ADD CONSTRAINT learning_sync_events_client_session_id_key
                    UNIQUE (client_session_id);
                END IF;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'learning_sync_events_client_session_id_key'
                  AND conrelid = 'learning_sync_events'::regclass
            ) THEN
                ALTER TABLE learning_sync_events
                DROP CONSTRAINT learning_sync_events_client_session_id_key;
            END IF;
        END
        $$;
        """
    )

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    user_columns = {column["name"] for column in inspector.get_columns("users")}

    if "role" in user_columns:
        op.drop_column("users", "role")

    user_role_enum.drop(bind, checkfirst=True)
