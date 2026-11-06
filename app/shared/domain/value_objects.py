"""Shared domain value objects used across multiple modules."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from app.shared.domain.errors import ValidationError


@dataclass(frozen=True)
class Money:
    """Monetary value with currency. Uses Decimal for precision.

    Amount must be non-negative. Currency defaults to PEN (Peruvian Sol).
    """

    amount: Decimal
    currency: str = "PEN"

    def __post_init__(self) -> None:
        if self.amount < Decimal("0"):
            raise ValidationError(
                message=f"El monto no puede ser negativo ({self.amount}). Corrígelo."
            )
        if not self.currency:
            raise ValidationError(message="Indica la moneda.")

    def __add__(self, other: Any) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        if self.currency != other.currency:
            raise ValidationError(
                message=f"No se pueden sumar montos en {self.currency} y {other.currency}. Usa una sola moneda."
            )
        return Money(amount=self.amount + other.amount, currency=self.currency)

    def __sub__(self, other: Any) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        if self.currency != other.currency:
            raise ValidationError(
                message=f"No se pueden restar montos en {self.currency} y {other.currency}. Usa una sola moneda."
            )
        result = self.amount - other.amount
        if result < Decimal("0"):
            raise ValidationError(
                message=f"El resultado sería un monto negativo ({result}). Revisa los importes."
            )
        return Money(amount=result, currency=self.currency)

    def __mul__(self, other: Any) -> Money:
        if isinstance(other, (int, Decimal)):
            return Money(amount=self.amount * Decimal(str(other)), currency=self.currency)
        return NotImplemented


@dataclass(frozen=True)
class Quantity:
    """Non-negative integer quantity."""

    value: int

    def __post_init__(self) -> None:
        if self.value < 0:
            raise ValidationError(
                message=f"La cantidad no puede ser negativa ({self.value}). Corrígela."
            )


@dataclass(frozen=True)
class Sku:
    """Stock Keeping Unit identifier. Normalized to uppercase, stripped.

    Must be non-empty after normalization.
    """

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().upper()
        if not normalized:
            raise ValidationError(message="El código (SKU) no puede estar vacío. Escríbelo.")
        # frozen dataclass: use object.__setattr__ to set the normalized value
        object.__setattr__(self, "value", normalized)


_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


@dataclass(frozen=True)
class Email:
    """Email address value object with basic format validation."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().lower()
        if not _EMAIL_RE.match(normalized):
            raise ValidationError(
                message=f"El correo «{self.value}» no es válido. Revísalo."
            )
        object.__setattr__(self, "value", normalized)


@dataclass(frozen=True)
class DateRange:
    """A date range [start, end] inclusive. Start must be <= end."""

    start: date
    end: date

    def __post_init__(self) -> None:
        if self.start > self.end:
            raise ValidationError(
                message=f"La fecha inicial ({self.start}) debe ser anterior o igual a la final ({self.end})."
            )

    @property
    def days(self) -> int:
        """Number of days in the range (inclusive)."""
        return (self.end - self.start).days + 1


@dataclass(frozen=True)
class Percentage:
    """Percentage value in the 0–100 scale (i.e., 50 means 50%).

    Design decision: We use the 0–100 scale because it is the most intuitive
    for business users and directly matches how KPIs and metrics are typically
    displayed in dashboards (e.g., "stockout risk: 75%").
    """

    value: Decimal

    def __post_init__(self) -> None:
        if self.value < Decimal("0") or self.value > Decimal("100"):
            raise ValidationError(
                message=f"El porcentaje debe estar entre 0 y 100 (recibido: {self.value})."
            )
