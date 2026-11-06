"""ERP v2: POS orders, sellers, costing, custom fields, lost sales, FTGM scope, billing payments

Revision ID: b7e1c3d9f420
Revises: 2d7ecfd5513c
Create Date: 2026-09-12

One migration for the whole ERP v2 schema so parallel module work never forks the
Alembic history:

* companies.next_product_code — global per-company product code correlativo.
* users.username (+ email nullable) — sellers log in with user/password, no email.
* products: barcode, image, custom attributes, last purchase cost.
* sales_orders — a POS ticket (cart) that groups sale lines, with the client's
  DNI/RUC, comprobante type, payment method and the seller who rang it up.
* sales: order_id / seller / unit_cost at sale time (margin).
* lost_sales — every time a seller tried to sell something without stock (quiebre).
* inventory_movements: unit cost + a reference to the sale order / purchase.
* suppliers.custom_attributes, purchases: supplier document number + import batch.
* custom_field_definitions / ui_preferences — user-defined columns and saved views.
* forecast_runs: the scope the run was launched with (last N months, supplier, seller).
* billing_payments — simulated checkout history for the Premium plan.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b7e1c3d9f420'
down_revision: Union[str, Sequence[str], None] = '2d7ecfd5513c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    ]


def upgrade() -> None:
    # --- companies / users ----------------------------------------------------
    op.add_column('companies', sa.Column('next_product_code', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('users', sa.Column('username', sa.String(length=60), nullable=True))
    op.create_index('ix_users_username', 'users', ['username'], unique=True)
    op.alter_column('users', 'email', existing_type=sa.String(length=255), nullable=True)

    # --- products -------------------------------------------------------------
    op.add_column('products', sa.Column('barcode', sa.String(length=64), nullable=True))
    op.create_index('ix_products_barcode', 'products', ['barcode'])
    op.add_column('products', sa.Column('image_url', sa.Text(), nullable=True))
    op.add_column('products', sa.Column('custom_attributes', sa.JSON(), nullable=False, server_default='{}'))
    op.add_column('products', sa.Column('last_cost', sa.Numeric(14, 2), nullable=True))

    # --- POS: sales orders ------------------------------------------------------
    op.create_table(
        'sales_orders',
        sa.Column('company_id', sa.Uuid(), nullable=False),
        sa.Column('order_number', sa.Integer(), nullable=False),
        sa.Column('seller_id', sa.Uuid(), nullable=True),
        sa.Column('seller_name', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('document_type', sa.String(length=12), nullable=False, server_default='boleta'),
        sa.Column('client_doc_type', sa.String(length=10), nullable=False, server_default='none'),
        sa.Column('client_doc_number', sa.String(length=11), nullable=False, server_default=''),
        sa.Column('client_name', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('client_address', sa.String(length=500), nullable=False, server_default=''),
        sa.Column('payment_method', sa.String(length=20), nullable=False, server_default='efectivo'),
        sa.Column('amount_received', sa.Numeric(14, 2), nullable=True),
        sa.Column('discount_total', sa.Numeric(14, 2), nullable=False, server_default='0'),
        sa.Column('subtotal', sa.Numeric(14, 2), nullable=False),
        sa.Column('igv', sa.Numeric(14, 2), nullable=False),
        sa.Column('total', sa.Numeric(14, 2), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='PEN'),
        sa.Column('status', sa.String(length=12), nullable=False, server_default='completed'),
        sa.Column('invoice_id', sa.Uuid(), nullable=True),
        sa.Column('notes', sa.String(length=500), nullable=False, server_default=''),
        sa.Column('sold_at', sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('company_id', 'order_number', name='uq_sales_orders_company_number'),
    )
    op.create_index('ix_sales_orders_company_id', 'sales_orders', ['company_id'])
    op.create_index('ix_sales_orders_seller_id', 'sales_orders', ['seller_id'])

    op.add_column('sales', sa.Column('order_id', sa.Uuid(), nullable=True))
    op.create_index('ix_sales_order_id', 'sales', ['order_id'])
    op.add_column('sales', sa.Column('seller_id', sa.Uuid(), nullable=True))
    op.add_column('sales', sa.Column('seller_name', sa.String(length=255), nullable=False, server_default=''))
    op.add_column('sales', sa.Column('unit_cost', sa.Numeric(14, 2), nullable=True))

    op.add_column('invoices', sa.Column('client_address', sa.String(length=500), nullable=False, server_default=''))

    # --- lost sales (quiebres at the till) ---------------------------------------
    op.create_table(
        'lost_sales',
        sa.Column('company_id', sa.Uuid(), nullable=False),
        sa.Column('product_id', sa.Uuid(), nullable=False),
        sa.Column('requested_quantity', sa.Integer(), nullable=False),
        sa.Column('available_quantity', sa.Integer(), nullable=False),
        sa.Column('seller_id', sa.Uuid(), nullable=True),
        sa.Column('seller_name', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('source', sa.String(length=20), nullable=False, server_default='pos'),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_lost_sales_company_id', 'lost_sales', ['company_id'])
    op.create_index('ix_lost_sales_product_id', 'lost_sales', ['product_id'])

    # --- inventory movements: cost + traceability ---------------------------------
    op.add_column('inventory_movements', sa.Column('unit_cost', sa.Numeric(14, 2), nullable=True))
    op.add_column('inventory_movements', sa.Column('reference_type', sa.String(length=20), nullable=True))
    op.add_column('inventory_movements', sa.Column('reference_id', sa.Uuid(), nullable=True))
    op.create_index('ix_inventory_movements_reference_id', 'inventory_movements', ['reference_id'])

    # --- suppliers / purchases ----------------------------------------------------
    op.add_column('suppliers', sa.Column('custom_attributes', sa.JSON(), nullable=False, server_default='{}'))
    op.add_column('purchases', sa.Column('document_number', sa.String(length=40), nullable=False, server_default=''))
    op.add_column('purchases', sa.Column('import_batch_id', sa.Uuid(), nullable=True))
    op.add_column('purchases', sa.Column('notes', sa.String(length=500), nullable=False, server_default=''))

    # --- custom fields + saved views -------------------------------------------------
    op.create_table(
        'custom_field_definitions',
        sa.Column('company_id', sa.Uuid(), nullable=False),
        sa.Column('entity', sa.String(length=20), nullable=False),
        sa.Column('key', sa.String(length=60), nullable=False),
        sa.Column('label', sa.String(length=120), nullable=False),
        sa.Column('field_type', sa.String(length=20), nullable=False, server_default='text'),
        sa.Column('options', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_visible', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('is_required', sa.Boolean(), nullable=False, server_default=sa.false()),
        *_timestamps(),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('company_id', 'entity', 'key', name='uq_custom_fields_company_entity_key'),
    )
    op.create_index('ix_custom_field_definitions_company_id', 'custom_field_definitions', ['company_id'])

    op.create_table(
        'ui_preferences',
        sa.Column('company_id', sa.Uuid(), nullable=False),
        sa.Column('key', sa.String(length=80), nullable=False),
        sa.Column('value', sa.JSON(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('company_id', 'key', name='uq_ui_preferences_company_key'),
    )
    op.create_index('ix_ui_preferences_company_id', 'ui_preferences', ['company_id'])

    # --- forecasting scope ---------------------------------------------------------------
    op.add_column('forecast_runs', sa.Column('scope', sa.JSON(), nullable=True))
    op.add_column('forecast_runs', sa.Column('product_ids', sa.JSON(), nullable=True))
    op.add_column('forecast_runs', sa.Column('frequency', sa.String(length=10), nullable=True))

    # --- billing payments -----------------------------------------------------------------
    op.create_table(
        'billing_payments',
        sa.Column('company_id', sa.Uuid(), nullable=False),
        sa.Column('plan_id', sa.String(length=50), nullable=False),
        sa.Column('billing_cycle', sa.String(length=10), nullable=False, server_default='monthly'),
        sa.Column('amount', sa.Numeric(14, 2), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='PEN'),
        sa.Column('method', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='paid'),
        sa.Column('reference', sa.String(length=40), nullable=False),
        sa.Column('card_last4', sa.String(length=4), nullable=True),
        sa.Column('paid_at', sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_billing_payments_company_id', 'billing_payments', ['company_id'])


def downgrade() -> None:
    op.drop_index('ix_billing_payments_company_id', table_name='billing_payments')
    op.drop_table('billing_payments')
    op.drop_column('forecast_runs', 'frequency')
    op.drop_column('forecast_runs', 'product_ids')
    op.drop_column('forecast_runs', 'scope')
    op.drop_index('ix_ui_preferences_company_id', table_name='ui_preferences')
    op.drop_table('ui_preferences')
    op.drop_index('ix_custom_field_definitions_company_id', table_name='custom_field_definitions')
    op.drop_table('custom_field_definitions')
    op.drop_column('purchases', 'notes')
    op.drop_column('purchases', 'import_batch_id')
    op.drop_column('purchases', 'document_number')
    op.drop_column('suppliers', 'custom_attributes')
    op.drop_index('ix_inventory_movements_reference_id', table_name='inventory_movements')
    op.drop_column('inventory_movements', 'reference_id')
    op.drop_column('inventory_movements', 'reference_type')
    op.drop_column('inventory_movements', 'unit_cost')
    op.drop_index('ix_lost_sales_product_id', table_name='lost_sales')
    op.drop_index('ix_lost_sales_company_id', table_name='lost_sales')
    op.drop_table('lost_sales')
    op.drop_column('invoices', 'client_address')
    op.drop_column('sales', 'unit_cost')
    op.drop_column('sales', 'seller_name')
    op.drop_column('sales', 'seller_id')
    op.drop_index('ix_sales_order_id', table_name='sales')
    op.drop_column('sales', 'order_id')
    op.drop_index('ix_sales_orders_seller_id', table_name='sales_orders')
    op.drop_index('ix_sales_orders_company_id', table_name='sales_orders')
    op.drop_table('sales_orders')
    op.drop_column('products', 'last_cost')
    op.drop_column('products', 'custom_attributes')
    op.drop_column('products', 'image_url')
    op.drop_index('ix_products_barcode', table_name='products')
    op.drop_column('products', 'barcode')
    op.alter_column('users', 'email', existing_type=sa.String(length=255), nullable=False)
    op.drop_index('ix_users_username', table_name='users')
    op.drop_column('users', 'username')
    op.drop_column('companies', 'next_product_code')
