"""Rich FTGM output: history on results, provenance + scaled metrics on metrics.

Revision ID: a91f2c47d310
Revises: e4b7c9a10f23
Create Date: 2026-07-04

forecast_results.history       — in-sample buckets (observed/cleaned/fitted) per product,
                                 so the real-vs-model chart is reproducible from the run.
forecast_metrics.mase/rmsse    — M5 scaled metrics from the paper (nullable: undefined
                                 for flat or all-zero series).
forecast_metrics.order_selected/model_used/status/fallback_reason/validation_rmse
                               — Algorithm 1 provenance: which model actually ran and why.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a91f2c47d310'
down_revision: Union[str, Sequence[str], None] = 'e4b7c9a10f23'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('forecast_results', sa.Column('history', sa.JSON(), nullable=True))

    op.add_column('forecast_metrics', sa.Column('mase', sa.Numeric(10, 4), nullable=True))
    op.add_column('forecast_metrics', sa.Column('rmsse', sa.Numeric(10, 4), nullable=True))
    op.add_column(
        'forecast_metrics',
        sa.Column('order_selected', sa.Integer(), nullable=False, server_default='0'),
    )
    op.add_column(
        'forecast_metrics',
        sa.Column('model_used', sa.String(length=50), nullable=False, server_default=''),
    )
    op.add_column(
        'forecast_metrics',
        sa.Column('status', sa.String(length=20), nullable=False, server_default='ok'),
    )
    op.add_column(
        'forecast_metrics', sa.Column('fallback_reason', sa.String(length=500), nullable=True)
    )
    op.add_column(
        'forecast_metrics', sa.Column('validation_rmse', sa.Numeric(14, 4), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('forecast_metrics', 'validation_rmse')
    op.drop_column('forecast_metrics', 'fallback_reason')
    op.drop_column('forecast_metrics', 'status')
    op.drop_column('forecast_metrics', 'model_used')
    op.drop_column('forecast_metrics', 'order_selected')
    op.drop_column('forecast_metrics', 'rmsse')
    op.drop_column('forecast_metrics', 'mase')
    op.drop_column('forecast_results', 'history')
