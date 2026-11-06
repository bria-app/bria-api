"""Sales module — mappers between ORM models and domain entities."""
from __future__ import annotations

from app.modules.sales.domain.entities import (
    LostSale,
    Sale,
    SalesBatch,
    SalesOrder,
    SalesOrderLine,
)
from app.modules.sales.domain.enums import (
    BatchStatus,
    ClientDocType,
    OrderStatus,
    PaymentMethod,
    SalesDocumentType,
)
from app.modules.sales.domain.services import lima_date
from app.modules.sales.infrastructure.persistence.models import (
    LostSaleModel,
    SaleModel,
    SalesBatchModel,
    SalesOrderModel,
)
from app.shared.domain.value_objects import DateRange, Money, Quantity


def batch_to_entity(model: SalesBatchModel) -> SalesBatch:
    period = None
    if model.period_start is not None and model.period_end is not None:
        period = DateRange(model.period_start, model.period_end)
    return SalesBatch(
        id=model.id,
        company_id=model.company_id,
        source_file=model.source_file,
        status=BatchStatus(model.status),
        row_count=model.row_count,
        period=period,
    )


def batch_to_model(entity: SalesBatch) -> SalesBatchModel:
    return SalesBatchModel(
        id=entity.id,
        company_id=entity.company_id,
        source_file=entity.source_file,
        status=entity.status.value,
        row_count=entity.row_count,
        period_start=entity.period.start if entity.period else None,
        period_end=entity.period.end if entity.period else None,
    )


def sale_to_entity(model: SaleModel, product_name: str = "", sku: str = "") -> Sale:
    return Sale(
        product_name=product_name,
        sku=sku,
        id=model.id,
        company_id=model.company_id,
        product_id=model.product_id,
        sale_date=model.sale_date,
        quantity=Quantity(model.quantity),
        unit_price=Money(model.unit_price, model.currency),
        total_amount=Money(model.total_amount, model.currency),
        batch_id=model.batch_id,
        order_id=model.order_id,
        seller_id=model.seller_id,
        seller_name=model.seller_name or "",
        unit_cost=model.unit_cost,
    )


def sale_to_model(entity: Sale) -> SaleModel:
    return SaleModel(
        id=entity.id,
        company_id=entity.company_id,
        product_id=entity.product_id,
        batch_id=entity.batch_id,
        sale_date=entity.sale_date,
        quantity=entity.quantity.value,
        unit_price=entity.unit_price.amount,
        total_amount=entity.total_amount.amount,
        currency=entity.unit_price.currency,
        order_id=entity.order_id,
        seller_id=entity.seller_id,
        seller_name=entity.seller_name,
        unit_cost=entity.unit_cost,
    )


# --- POS -----------------------------------------------------------------------
def order_to_model(entity: SalesOrder) -> SalesOrderModel:
    return SalesOrderModel(
        id=entity.id,
        company_id=entity.company_id,
        order_number=entity.order_number,
        seller_id=entity.seller_id,
        seller_name=entity.seller_name,
        document_type=entity.document_type.value,
        client_doc_type=entity.client_doc_type.value,
        client_doc_number=entity.client_doc_number,
        client_name=entity.client_name,
        client_address=entity.client_address,
        payment_method=entity.payment_method.value,
        amount_received=entity.amount_received,
        discount_total=entity.discount_total,
        subtotal=entity.subtotal,
        igv=entity.igv,
        total=entity.total,
        currency=entity.currency,
        status=entity.status.value,
        invoice_id=entity.invoice_id,
        notes=entity.notes,
        sold_at=entity.sold_at,
    )


def order_line_to_model(order: SalesOrder, line: SalesOrderLine) -> SaleModel:
    return SaleModel(
        company_id=order.company_id,
        product_id=line.product_id,
        batch_id=None,
        sale_date=lima_date(order.sold_at),
        quantity=line.quantity,
        unit_price=line.unit_price,
        total_amount=line.line_total,
        currency=order.currency,
        order_id=order.id,
        seller_id=order.seller_id,
        seller_name=order.seller_name,
        unit_cost=line.unit_cost,
    )


def line_to_entity(model: SaleModel, product_name: str = "", sku: str = "") -> SalesOrderLine:
    return SalesOrderLine(
        id=model.id,
        product_id=model.product_id,
        quantity=model.quantity,
        unit_price=model.unit_price,
        discount=model.unit_price * model.quantity - model.total_amount,
        unit_cost=model.unit_cost,
        product_name=product_name,
        sku=sku,
    )


def order_to_entity(model: SalesOrderModel, lines: list[SalesOrderLine]) -> SalesOrder:
    return SalesOrder(
        id=model.id,
        company_id=model.company_id,
        order_number=model.order_number,
        document_type=SalesDocumentType(model.document_type),
        client_doc_type=ClientDocType(model.client_doc_type),
        client_doc_number=model.client_doc_number,
        client_name=model.client_name,
        client_address=model.client_address,
        payment_method=PaymentMethod(model.payment_method),
        lines=lines,
        sold_at=model.sold_at,
        seller_id=model.seller_id,
        seller_name=model.seller_name,
        amount_received=model.amount_received,
        notes=model.notes,
        currency=model.currency,
        status=OrderStatus(model.status),
        invoice_id=model.invoice_id,
    )


def lost_sale_to_model(entity: LostSale) -> LostSaleModel:
    return LostSaleModel(
        id=entity.id,
        company_id=entity.company_id,
        product_id=entity.product_id,
        requested_quantity=entity.requested_quantity,
        available_quantity=entity.available_quantity,
        seller_id=entity.seller_id,
        seller_name=entity.seller_name,
        source=entity.source,
        occurred_at=entity.occurred_at,
    )


def lost_sale_to_entity(model: LostSaleModel) -> LostSale:
    return LostSale(
        id=model.id,
        company_id=model.company_id,
        product_id=model.product_id,
        requested_quantity=model.requested_quantity,
        available_quantity=model.available_quantity,
        seller_id=model.seller_id,
        seller_name=model.seller_name,
        source=model.source,
        occurred_at=model.occurred_at,
    )
