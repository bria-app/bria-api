"""Custom fields scoped to product types (categories)

Revision ID: c5d2e8a4b713
Revises: b7e1c3d9f420
Create Date: 2026-09-13

A product column can apply to every product (empty list, the default and how every
existing column keeps behaving) or only to products under some categories — e.g.
"Talla" for Ropa and "Voltaje" for Electro, both living in the same inventory.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c5d2e8a4b713'
down_revision: Union[str, Sequence[str], None] = 'b7e1c3d9f420'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'custom_field_definitions',
        sa.Column('category_ids', sa.JSON(), nullable=False, server_default='[]'),
    )


def downgrade() -> None:
    op.drop_column('custom_field_definitions', 'category_ids')
