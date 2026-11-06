"""forecast_metrics: MAPE / MAE / RMSE nullable

Revision ID: d8f3a6b2c901
Revises: c5d2e8a4b713
Create Date: 2026-11-02

The engine returns ``mape = null`` when every actual in the evaluation window is 0 (and
may omit other metrics). Those values used to be coerced to 0, which reads as a
*perfect* forecast. They are now stored as NULL (audit M-10).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd8f3a6b2c901'
down_revision: Union[str, Sequence[str], None] = 'c5d2e8a4b713'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = (('mape', sa.Numeric(10, 4)), ('mae', sa.Numeric(14, 4)), ('rmse', sa.Numeric(14, 4)))


def upgrade() -> None:
    with op.batch_alter_table('forecast_metrics') as batch:
        for name, type_ in _COLUMNS:
            batch.alter_column(name, existing_type=type_, nullable=True)


def downgrade() -> None:
    for name, _ in _COLUMNS:
        op.execute(f"UPDATE forecast_metrics SET {name} = 0 WHERE {name} IS NULL")
    with op.batch_alter_table('forecast_metrics') as batch:
        for name, type_ in _COLUMNS:
            batch.alter_column(name, existing_type=type_, nullable=False)
