"""owner_id de connections y ktr_build_jobs a String (claim sub JWT)

Revision ID: 1093a39ce719
Revises: c3a4b5d6e7f8
Create Date: 2026-07-19 16:58:54.503699

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1093a39ce719'
down_revision: Union[str, None] = 'c3a4b5d6e7f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# owner_id pasa a guardar el claim "sub" del JWT (Auth0: "auth0|...",
# "google-oauth2|...") en vez de un UUID — nunca fue un UUID real, era
# simplemente el tipo que se eligió antes de tener ownership real conectado.
# ktr_build_jobs.owner_id nunca tuvo una migración propia (la tabla se crea
# vía Base.metadata.create_all, no vía Alembic) pero ya existe en el schema
# real con el tipo viejo — se altera igual, Alembic no necesita haber creado
# la tabla para poder alterarla.
_TABLES = ("connections", "ktr_build_jobs")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        for table in _TABLES:
            with op.batch_alter_table(table) as batch_op:
                batch_op.alter_column(
                    "owner_id",
                    existing_type=sa.Uuid(),
                    type_=sa.String(255),
                    existing_nullable=True,
                )
    else:
        for table in _TABLES:
            op.alter_column(
                table, "owner_id",
                existing_type=sa.Uuid(),
                type_=sa.String(255),
                existing_nullable=True,
                postgresql_using="owner_id::text",
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        for table in _TABLES:
            with op.batch_alter_table(table) as batch_op:
                batch_op.alter_column(
                    "owner_id",
                    existing_type=sa.String(255),
                    type_=sa.Uuid(),
                    existing_nullable=True,
                )
    else:
        for table in _TABLES:
            op.alter_column(
                table, "owner_id",
                existing_type=sa.String(255),
                type_=sa.Uuid(),
                existing_nullable=True,
                postgresql_using="owner_id::uuid",
            )
