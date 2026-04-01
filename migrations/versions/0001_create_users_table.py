"""create users table

Revision ID: 0001_create_users_table
Revises:
Create Date: 2026-03-31 00:00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "0001_create_users_table"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


subscription_plan_enum = postgresql.ENUM(
    "free",
    "semi_premium",
    "premium",
    name="subscriptionplan",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    subscription_plan_enum.create(bind, checkfirst=True)
    inspector = sa.inspect(bind)

    if not inspector.has_table("users"):
        op.create_table(
            "users",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("firebase_uid", sa.String(), nullable=False),
            sa.Column("email", sa.String(), nullable=False),
            sa.Column("name", sa.String(), nullable=True),
            sa.Column(
                "subscription_plan",
                subscription_plan_enum,
                nullable=False,
                server_default="free",
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("email"),
            sa.UniqueConstraint("firebase_uid"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("users"):
        op.drop_table("users")

    subscription_plan_enum.drop(bind, checkfirst=True)
