"""create connections table

Revision ID: c3a4b5d6e7f8
Revises:
Create Date: 2026-05-15 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3a4b5d6e7f8"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "db_type",
            sa.Enum("postgresql", "sqlserver", name="db_type_enum"),
            nullable=False,
        ),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("database", sa.String(255), nullable=False),
        sa.Column("username", sa.String(255), nullable=False),
        sa.Column("encrypted_password", sa.LargeBinary(), nullable=False),
        sa.Column("ssl_mode", sa.String(64), nullable=True),
        sa.Column("extra_options", sa.JSON(), nullable=True),
        sa.Column("owner_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_test_status",
            sa.Enum("success", "failed", "never", name="test_status_enum"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_connections"),
        sa.UniqueConstraint("owner_id", "name", name="uq_connections_owner_name"),
    )
    op.create_index("ix_connections_owner_id", "connections", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_connections_owner_id", table_name="connections")
    op.drop_table("connections")
    op.execute("DROP TYPE IF EXISTS test_status_enum")
    op.execute("DROP TYPE IF EXISTS db_type_enum")
