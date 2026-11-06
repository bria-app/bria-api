"""Data preparation — pipeline use case: prepare a dataset from an ingestion batch."""
from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from app.modules.data_preparation.application.dtos import PreparedDatasetDTO
from app.modules.data_preparation.application.ports import DemandRowParser
from app.modules.data_preparation.domain.entities import (
    PreparedDataset,
    PreparedTimeSeries,
)
from app.modules.data_preparation.domain.enums import DatasetStatus
from app.modules.data_preparation.domain.exceptions import InvalidDatasetError
from app.modules.data_preparation.domain.repositories import (
    PreparedDatasetRepository,
)
from app.modules.data_preparation.domain.services import prepare_demand_series
from app.modules.data_preparation.domain.value_objects import DemandRecord
from app.modules.ingestion.domain.exceptions import IngestionBatchNotFoundError
from app.modules.ingestion.domain.repositories import IngestionBatchRepository
from app.modules.inventory.domain.entities import InventoryMovement
from app.modules.inventory.domain.enums import MovementType
from app.modules.inventory.domain.repositories import InventoryMovementRepository
from app.modules.products.domain.repositories import ProductRepository
from app.modules.sales.domain.entities import Sale
from app.modules.sales.domain.repositories import SaleRepository
from app.shared.application.ports import StoragePort
from app.shared.domain.value_objects import DateRange, Money, Quantity

# Reason tag for auto-seeded opening stock, so re-preparing can replace it idempotently.
_OPENING_STOCK_REASON = "Stock inicial (auto)"
# Deterministic factors applied to each product's reorder point, cycled by product
# order. The reorder point is the natural inventory anchor: stock below it means
# "time to reorder". The spread (0.25×–4×) yields a realistic portfolio — some products
# critically low (reorder now), some healthy, some overstocked — so the decision layer
# (inventory status, KPIs, recommendations) shows meaningful variety, not a flat wall.
_OPENING_STOCK_FACTORS = [0.25, 1.6, 0.7, 3.0, 0.4, 1.1, 0.55, 2.2, 0.3, 1.8, 4.0, 0.9]


class PrepareDatasetFromBatch:
    def __init__(
        self,
        *,
        batches: IngestionBatchRepository,
        products: ProductRepository,
        datasets: PreparedDatasetRepository,
        storage: StoragePort,
        sales: SaleRepository,
        movements: InventoryMovementRepository,
        parse_rows: DemandRowParser,
    ) -> None:
        self._batches = batches
        self._products = products
        self._datasets = datasets
        self._storage = storage
        self._sales = sales
        self._movements = movements
        self._parse_rows = parse_rows

    def execute(
        self,
        company_id: UUID,
        *,
        batch_id: UUID,
        treat_zero_as_stockout: bool = False,
    ) -> PreparedDatasetDTO:
        batch = self._batches.get_by_id(batch_id)
        if batch is None or batch.company_id != company_id:
            raise IngestionBatchNotFoundError(
                message="No encontramos esa carga de archivo. Actualiza la página e inténtalo de nuevo."
            )

        content = self._storage.get(batch.file_path)
        raw_rows = self._parse_rows(
            content=content,
            file_type=batch.file_type,
            column_mapping=batch.column_mapping,
        )

        # Resolve SKUs to product ids; unknown SKUs are skipped. In the same pass we
        # materialize individual sale transactions (priced from the product catalog) so
        # the Sales view reflects exactly what was uploaded — the raw rows carry no price.
        records: list[DemandRecord] = []
        sales_to_add: list[Sale] = []
        for row in raw_rows:
            product = self._products.get_by_sku(company_id, row.sku)
            if product is None or product.id is None:
                continue
            records.append(
                DemandRecord(
                    product_id=product.id,
                    period_date=row.period_date,
                    quantity=row.quantity,
                    is_stockout=row.is_stockout,
                )
            )
            qty = int(row.quantity)
            if qty > 0:
                price = Money(product.unit_price.amount, product.unit_price.currency)
                sales_to_add.append(
                    Sale(
                        company_id=company_id,
                        product_id=product.id,
                        sale_date=row.period_date,
                        quantity=Quantity(qty),
                        unit_price=price,
                        total_amount=price * qty,
                        batch_id=batch_id,
                    )
                )

        if not records:
            raise InvalidDatasetError(
                message="No se pudo preparar ninguna fila: el archivo está vacío o sus códigos no coinciden con tus productos. Revisa la columna SKU."
            )

        # Replace any sales previously materialized from this batch (idempotent
        # re-prepare), then persist the fresh set.
        self._sales.delete_by_batch(company_id, batch_id)
        if sales_to_add:
            self._sales.add_bulk(sales_to_add)

        prepared = prepare_demand_series(
            records, treat_zero_as_stockout=treat_zero_as_stockout
        )

        dataset_id = uuid4()
        series = [
            PreparedTimeSeries(
                dataset_id=dataset_id,
                product_id=p.product_id,
                points=p.points,
                has_stockout_flags=p.has_stockout_flags,
                outliers_treated=p.outliers_treated,
            )
            for p in prepared
        ]

        all_dates: list[date] = [pt.period_date for s in series for pt in s.points]
        period = DateRange(min(all_dates), max(all_dates)) if all_dates else None

        # Seed a realistic opening stock per product so the decision layer (inventory,
        # KPIs, recommendations) has real on-hand levels to work with.
        self._seed_opening_stock(company_id, series)

        dataset = PreparedDataset(
            id=dataset_id,
            company_id=company_id,
            source_batch_id=batch_id,
            status=DatasetStatus.READY,
            product_count=len(series),
            period=period,
            series=series,
        )
        return PreparedDatasetDTO.from_entity(self._datasets.add(dataset))

    def _seed_opening_stock(
        self, company_id: UUID, series: list[PreparedTimeSeries]
    ) -> None:
        """Create one INBOUND opening-stock movement per product (idempotent).

        Opening stock = reorder point × a per-product factor. When a product has no
        reorder point set, fall back to ~1 month of demand so it still gets sensible
        stock. Stock varies across the catalog so the decision layer is meaningful.
        """
        now = datetime.now(timezone.utc)
        reorder_by_id = {
            p.id: p.reorder_point
            for p in self._products.list_active(company_id)
            if p.id is not None
        }
        # Stable order -> stable factor assignment across re-preparations.
        ordered = sorted(series, key=lambda s: str(s.product_id))
        movements: list[InventoryMovement] = []
        for idx, s in enumerate(ordered):
            if not s.points:
                continue
            factor = _OPENING_STOCK_FACTORS[idx % len(_OPENING_STOCK_FACTORS)]
            reorder = reorder_by_id.get(s.product_id, 0)
            if reorder > 0:
                opening = max(1, round(reorder * factor))
            else:
                # No reorder policy: fall back to ~1 month of demand scaled by the factor.
                dates = [pt.period_date for pt in s.points]
                span_days = (max(dates) - min(dates)).days + 1
                monthly = sum(float(pt.demand) for pt in s.points) / max(1.0, span_days / 30.44)
                opening = max(1, round(monthly * factor))
            movements.append(
                InventoryMovement(
                    company_id=company_id,
                    product_id=s.product_id,
                    movement_type=MovementType.INBOUND,
                    quantity=Quantity(opening),
                    reason=_OPENING_STOCK_REASON,
                    occurred_at=now,
                )
            )
        # Replace prior auto-seeded stock, then insert the fresh set.
        self._movements.delete_by_reason(company_id, _OPENING_STOCK_REASON)
        if movements:
            self._movements.add_bulk(movements)
