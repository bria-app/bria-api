"""Advanced rules for custom fields (validation and one alert per column)

Revision ID: f3a9c1d7e5b2
Revises: d8f3a6b2c901
Create Date: 2026-11-05

A column may carry {"validation": {...}, "alert": {...}}: what a value must look like
(max length, only digits, min/max, no future dates...) and a condition that marks the
product as needing attention («Por vencer»). Every existing column gets {} (no rules)
and keeps behaving as before.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'f3a9c1d7e5b2'
down_revision: Union[str, Sequence[str], None] = 'd8f3a6b2c901'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'custom_field_definitions',
        sa.Column('rules', sa.JSON(), nullable=False, server_default='{}'),
    )


def downgrade() -> None:
    op.drop_column('custom_field_definitions', 'rules')
