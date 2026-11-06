"""Inventory module domain — enums."""
from __future__ import annotations

from enum import StrEnum


class MovementType(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    ADJUSTMENT = "adjustment"


class ReplenishmentStatus(StrEnum):
    SUGGESTED = "suggested"
    ORDERED = "ordered"
    RECEIVED = "received"
    CANCELLED = "cancelled"


class AdjustmentMode(StrEnum):
    SET = "set"      # physical count: the new on-hand quantity
    DELTA = "delta"  # signed change (+ found / − shrinkage)


class AdjustmentReason(StrEnum):
    CONTEO = "conteo"
    MERMA = "merma"
    ROBO = "robo"
    VENCIDO = "vencido"
    OTRO = "otro"

    @property
    def label(self) -> str:
        return _REASON_LABELS[self]

    @property
    def only_reduces(self) -> bool:
        return self in (AdjustmentReason.MERMA, AdjustmentReason.ROBO, AdjustmentReason.VENCIDO)


_REASON_LABELS = {
    AdjustmentReason.CONTEO: "Conteo físico",
    AdjustmentReason.MERMA: "Merma",
    AdjustmentReason.ROBO: "Robo o pérdida",
    AdjustmentReason.VENCIDO: "Producto vencido",
    AdjustmentReason.OTRO: "Otro motivo",
}
