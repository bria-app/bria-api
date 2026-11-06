"""Purchases module domain — IGV handling.

Inventory is valued NET of IGV: in Peru the IGV paid on purchases is crédito fiscal
(recoverable), so it is not part of the cost of the goods. When the user types costs
that already include IGV we divide by 1.18 and store the net unit cost; purchase lines,
product average cost and movement valuations are therefore always net amounts, and the
IGV is only computed for display (subtotal · IGV · total).
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

IGV_RATE = Decimal("0.18")
_CENT = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(_CENT, rounding=ROUND_HALF_UP)


def net_of_igv(amount: Decimal) -> Decimal:
    return money(Decimal(amount) / (Decimal("1") + IGV_RATE))


def igv_of(net_amount: Decimal) -> Decimal:
    return money(Decimal(net_amount) * IGV_RATE)
