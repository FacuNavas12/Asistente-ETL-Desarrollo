"""drop encrypted_password de connections

Revision ID: 6d7d3baba4c1
Revises: 1093a39ce719
Create Date: 2026-07-20 18:47:52.715045

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6d7d3baba4c1'
down_revision: Union[str, None] = '1093a39ce719'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Decisión de diseño: el backend deja de custodiar contraseñas de conexiones
# de origen/destino — el usuario las reingresa en cada operación que
# realmente conecta (test, exploración de esquema) y el .ktr las deja como
# variable de Kettle en vez de embeberlas. Ver discusión de "cambio de diseño
# — no persistir credenciales" en el historial del proyecto.


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("connections") as batch_op:
            batch_op.drop_column("encrypted_password")
    else:
        op.drop_column("connections", "encrypted_password")


def downgrade() -> None:
    # Reversible solo estructuralmente: la columna vuelve vacía (nullable),
    # no hay forma de reconstituir contraseñas que ya no se cifraron nunca.
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("connections") as batch_op:
            batch_op.add_column(sa.Column("encrypted_password", sa.LargeBinary(), nullable=True))
    else:
        op.add_column("connections", sa.Column("encrypted_password", sa.LargeBinary(), nullable=True))
