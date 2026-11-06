"""Suppliers, purchases and Peru-style invoicing (boleta/factura)

Revision ID: 2d7ecfd5513c
Revises: a91f2c47d310
Create Date: 2026-09-12

Closes the ERP loop on the supply side: Suppliers (RUC + contact data) feed
Purchases (which push stock in via an inbound movement), and Invoicing issues
Boleta/Factura documents with Peru's 18% IGV and a per-series correlativo —
the same shape SUNAT comprobantes use, without the electronic-submission part
(out of scope for this academic prototype).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '2d7ecfd5513c'
down_revision: Union[str, Sequence[str], None] = 'a91f2c47d310'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'suppliers',
        sa.Column('company_id', sa.Uuid(), nullable=False),
        sa.Column('ruc', sa.String(length=11), nullable=False),
        sa.Column('business_name', sa.String(length=255), nullable=False),
        sa.Column('contact_name', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('phone', sa.String(length=30), nullable=False, server_default=''),
        sa.Column('email', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('address', sa.String(length=500), nullable=False, server_default=''),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_suppliers_company_id', 'suppliers', ['company_id'])

    op.create_table(
        'purchases',
        sa.Column('company_id', sa.Uuid(), nullable=False),
        sa.Column('supplier_id', sa.Uuid(), nullable=False),
        sa.Column('product_id', sa.Uuid(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('unit_cost', sa.Numeric(14, 2), nullable=False),
        sa.Column('total_amount', sa.Numeric(14, 2), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='PEN'),
        sa.Column('purchase_date', sa.Date(), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_purchases_company_id', 'purchases', ['company_id'])
    op.create_index('ix_purchases_supplier_id', 'purchases', ['supplier_id'])
    op.create_index('ix_purchases_product_id', 'purchases', ['product_id'])

    op.create_table(
        'invoices',
        sa.Column('company_id', sa.Uuid(), nullable=False),
        sa.Column('document_type', sa.String(length=10), nullable=False),
        sa.Column('series', sa.String(length=4), nullable=False),
        sa.Column('correlativo', sa.Integer(), nullable=False),
        sa.Column('client_doc_type', sa.String(length=10), nullable=False, server_default='none'),
        sa.Column('client_doc_number', sa.String(length=11), nullable=False, server_default=''),
        sa.Column('client_name', sa.String(length=255), nullable=False, server_default='Público en general'),
        sa.Column('items', sa.JSON(), nullable=False),
        sa.Column('subtotal', sa.Numeric(14, 2), nullable=False),
        sa.Column('igv', sa.Numeric(14, 2), nullable=False),
        sa.Column('total', sa.Numeric(14, 2), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='PEN'),
        sa.Column('status', sa.String(length=10), nullable=False, server_default='emitida'),
        sa.Column('issued_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('sale_id', sa.Uuid(), nullable=True),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('company_id', 'series', 'correlativo', name='uq_invoices_company_series_correlativo'),
    )
    op.create_index('ix_invoices_company_id', 'invoices', ['company_id'])


def downgrade() -> None:
    op.drop_index('ix_invoices_company_id', table_name='invoices')
    op.drop_table('invoices')
    op.drop_index('ix_purchases_product_id', table_name='purchases')
    op.drop_index('ix_purchases_supplier_id', table_name='purchases')
    op.drop_index('ix_purchases_company_id', table_name='purchases')
    op.drop_table('purchases')
    op.drop_index('ix_suppliers_company_id', table_name='suppliers')
    op.drop_table('suppliers')
