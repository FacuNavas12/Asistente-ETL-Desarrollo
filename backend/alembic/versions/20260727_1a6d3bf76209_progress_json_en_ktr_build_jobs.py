"""progress_json en ktr_build_jobs (D29)

Revision ID: 1a6d3bf76209
Revises: 6d7d3baba4c1
Create Date: 2026-07-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1a6d3bf76209'
down_revision: Union[str, None] = '6d7d3baba4c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# D29 (docs/refactor/02-decisiones.md): bitácora de progreso del job async de
# generación de ETL — {"next_seq": int, "truncated": bool, "events": [...]}.
# Único escritor: app/services/job_progress.py, sesión propia y corta.
#
# Guard obligatoria: ktr_build_jobs no fue creada por ninguna migración Alembic
# (ver el comentario en 20260719_1093a39ce719_*.py) — en el schema real existe
# porque se creó una vez vía Base.metadata.create_all antes de que el proyecto
# migrara a Alembic para todo. create_tables() no tiene ningún caller en el
# código de la app hoy, así que una DB de desarrollo fresca puede no tener la
# tabla todavía — add_column reventaría ahí sin este guard.
_TABLE = "ktr_build_jobs"
_COLUMN = "progress_json"


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if _TABLE not in insp.get_table_names():
        return
    if _COLUMN in {c["name"] for c in insp.get_columns(_TABLE)}:
        return
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(_TABLE) as batch_op:
            batch_op.add_column(sa.Column(_COLUMN, sa.JSON(), nullable=True))
    else:
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.JSON(), nullable=True))


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if _TABLE not in insp.get_table_names():
        return
    if _COLUMN not in {c["name"] for c in insp.get_columns(_TABLE)}:
        return
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(_TABLE) as batch_op:
            batch_op.drop_column(_COLUMN)
    else:
        op.drop_column(_TABLE, _COLUMN)
