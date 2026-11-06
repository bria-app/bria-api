"""Unit tests for domain layer — value objects, entities, and invariants."""
from __future__ import annotations

import pytest
from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.shared.domain.errors import ValidationError
from app.shared.domain.value_objects import (
    DateRange,
    Email,
    Money,
    Percentage,
    Quantity,
    Sku,
)
from app.modules.products.domain.entities import Product
from app.modules.products.domain.exceptions import InvalidProductError
from app.modules.forecasting.domain.entities import ForecastRun
from app.modules.forecasting.domain.enums import RunStatus
from app.modules.forecasting.domain.exceptions import InvalidRunTransitionError
from app.modules.sales.domain.entities import Sale
from app.modules.sales.domain.exceptions import InvalidSaleError
from app.modules.data_preparation.domain.entities import (
    PreparedDataset,
    PreparedTimeSeries,
)


# ---------------------------------------------------------------------------
# Value Object tests: Money
# ---------------------------------------------------------------------------

class TestMoney:
    def test_valid_money(self) -> None:
        m = Money(amount=Decimal("100.50"), currency="PEN")
        assert m.amount == Decimal("100.50")
        assert m.currency == "PEN"

    def test_zero_amount(self) -> None:
        m = Money(amount=Decimal("0"))
        assert m.amount == Decimal("0")

    def test_negative_amount_raises(self) -> None:
        with pytest.raises(ValidationError, match="no puede ser negativo"):
            Money(amount=Decimal("-1"))

    def test_add_same_currency(self) -> None:
        a = Money(amount=Decimal("10"), currency="PEN")
        b = Money(amount=Decimal("20"), currency="PEN")
        result = a + b
        assert result.amount == Decimal("30")

    def test_add_different_currency_raises(self) -> None:
        a = Money(amount=Decimal("10"), currency="PEN")
        b = Money(amount=Decimal("20"), currency="USD")
        with pytest.raises(ValidationError, match="una sola moneda"):
            _ = a + b

    def test_multiply_by_int(self) -> None:
        m = Money(amount=Decimal("5"), currency="PEN")
        result = m * 3
        assert result.amount == Decimal("15")


# ---------------------------------------------------------------------------
# Value Object tests: DateRange
# ---------------------------------------------------------------------------

class TestDateRange:
    def test_valid_range(self) -> None:
        dr = DateRange(start=date(2024, 1, 1), end=date(2024, 1, 31))
        assert dr.days == 31

    def test_single_day_range(self) -> None:
        dr = DateRange(start=date(2024, 6, 15), end=date(2024, 6, 15))
        assert dr.days == 1

    def test_invalid_range_raises(self) -> None:
        with pytest.raises(ValidationError, match="anterior o igual"):
            DateRange(start=date(2024, 12, 31), end=date(2024, 1, 1))


# ---------------------------------------------------------------------------
# Value Object tests: others
# ---------------------------------------------------------------------------

class TestOtherVOs:
    def test_sku_normalizes(self) -> None:
        s = Sku(value="  abc-123  ")
        assert s.value == "ABC-123"

    def test_sku_empty_raises(self) -> None:
        with pytest.raises(ValidationError, match="no puede estar vacío"):
            Sku(value="   ")

    def test_email_valid(self) -> None:
        e = Email(value="Test@Example.COM")
        assert e.value == "test@example.com"

    def test_email_invalid_raises(self) -> None:
        with pytest.raises(ValidationError, match="no es válido"):
            Email(value="not-an-email")

    def test_quantity_negative_raises(self) -> None:
        with pytest.raises(ValidationError, match="no puede ser negativa"):
            Quantity(value=-1)

    def test_percentage_out_of_range_raises(self) -> None:
        with pytest.raises(ValidationError, match="entre 0 y 100"):
            Percentage(value=Decimal("101"))


# ---------------------------------------------------------------------------
# Entity tests: ForecastRun state transitions
# ---------------------------------------------------------------------------

class TestForecastRunTransitions:
    def _make_run(self) -> ForecastRun:
        return ForecastRun(
            company_id=uuid4(),
            model_name="ftgm",
            horizon_days=30,
        )

    def test_pending_to_running(self) -> None:
        run = self._make_run()
        assert run.status == RunStatus.PENDING
        run.start()
        assert run.status == RunStatus.RUNNING  # type: ignore[comparison-overlap]
        assert run.started_at is not None

    def test_running_to_success(self) -> None:
        run = self._make_run()
        run.start()
        run.complete()
        assert run.status == RunStatus.SUCCESS
        assert run.completed_at is not None

    def test_running_to_failed(self) -> None:
        run = self._make_run()
        run.start()
        run.fail("timeout")
        assert run.status == RunStatus.FAILED
        assert run.error_message == "timeout"

    def test_pending_to_cancelled(self) -> None:
        run = self._make_run()
        run.cancel()
        assert run.status == RunStatus.CANCELLED

    def test_cannot_complete_pending_run(self) -> None:
        run = self._make_run()
        with pytest.raises(InvalidRunTransitionError, match="no puede pasar de"):
            run.complete()

    def test_cannot_start_completed_run(self) -> None:
        run = self._make_run()
        run.start()
        run.complete()
        with pytest.raises(InvalidRunTransitionError, match="no puede pasar de"):
            run.start()

    def test_cannot_cancel_completed_run(self) -> None:
        run = self._make_run()
        run.start()
        run.complete()
        with pytest.raises(InvalidRunTransitionError):
            run.cancel()


# ---------------------------------------------------------------------------
# Entity tests: Product invariants
# ---------------------------------------------------------------------------

class TestProductInvariants:
    def _make_product(self, **kwargs: object) -> Product:
        defaults: dict[str, object] = {
            "company_id": uuid4(),
            "sku": Sku("PROD-001"),
            "name": "Test Product",
            "unit_cost": Money(Decimal("10")),
            "unit_price": Money(Decimal("15")),
            "reorder_point": 5,
        }
        defaults.update(kwargs)
        return Product(**defaults)  # type: ignore[arg-type]

    def test_needs_reorder_at_reorder_point(self) -> None:
        p = self._make_product(reorder_point=10)
        assert p.needs_reorder(on_hand=10) is True

    def test_needs_reorder_below_reorder_point(self) -> None:
        p = self._make_product(reorder_point=10)
        assert p.needs_reorder(on_hand=5) is True

    def test_no_reorder_above_point(self) -> None:
        p = self._make_product(reorder_point=10)
        assert p.needs_reorder(on_hand=11) is False

    def test_inactive_product_does_not_need_reorder(self) -> None:
        p = self._make_product(reorder_point=10)
        p.deactivate()
        assert p.needs_reorder(on_hand=0) is False

    def test_negative_lead_time_raises(self) -> None:
        with pytest.raises(InvalidProductError, match="tiempo de reposición"):
            self._make_product(lead_time_days=-1)

    def test_negative_safety_stock_raises(self) -> None:
        with pytest.raises(InvalidProductError, match="stock de seguridad"):
            self._make_product(safety_stock=-1)


# ---------------------------------------------------------------------------
# Entity tests: Sale invariant
# ---------------------------------------------------------------------------

class TestSaleInvariant:
    def test_valid_sale(self) -> None:
        s = Sale(
            company_id=uuid4(),
            product_id=uuid4(),
            sale_date=date(2024, 6, 15),
            quantity=Quantity(3),
            unit_price=Money(Decimal("10")),
            total_amount=Money(Decimal("30")),
        )
        assert s.total_amount.amount == Decimal("30")

    def test_mismatched_total_raises(self) -> None:
        with pytest.raises(InvalidSaleError, match="no coincide"):
            Sale(
                company_id=uuid4(),
                product_id=uuid4(),
                sale_date=date(2024, 6, 15),
                quantity=Quantity(3),
                unit_price=Money(Decimal("10")),
                total_amount=Money(Decimal("25")),
            )

    def test_currency_mismatch_raises(self) -> None:
        with pytest.raises(InvalidSaleError, match="una sola moneda"):
            Sale(
                company_id=uuid4(),
                product_id=uuid4(),
                sale_date=date(2024, 6, 15),
                quantity=Quantity(2),
                unit_price=Money(Decimal("10"), currency="PEN"),
                total_amount=Money(Decimal("20"), currency="USD"),
            )


# ---------------------------------------------------------------------------
# Aggregate tests: PreparedDataset owns its PreparedTimeSeries children
# ---------------------------------------------------------------------------
class TestPreparedDatasetAggregate:
    def test_time_series_carries_dataset_back_reference(self) -> None:
        dataset_id = uuid4()
        series = PreparedTimeSeries(dataset_id=dataset_id, product_id=uuid4())
        assert series.dataset_id == dataset_id

    def test_dataset_aggregates_its_series(self) -> None:
        dataset = PreparedDataset(company_id=uuid4())
        assert dataset.series == []
        dataset.series.append(
            PreparedTimeSeries(dataset_id=uuid4(), product_id=uuid4())
        )
        assert len(dataset.series) == 1
