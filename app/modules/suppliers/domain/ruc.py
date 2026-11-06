"""Suppliers module domain — Peruvian RUC validation (SUNAT módulo 11)."""
from __future__ import annotations

_WEIGHTS = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
_VALID_PREFIXES = ("10", "15", "17", "20")


def normalize_ruc(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def ruc_check_digit(first_ten: str) -> int:
    total = sum(int(d) * w for d, w in zip(first_ten, _WEIGHTS))
    digit = 11 - (total % 11)
    if digit == 10:
        return 0
    if digit == 11:
        return 1
    return digit


def ruc_error(ruc: str) -> str | None:
    """Return a Spanish error message when `ruc` is not a valid RUC, else None."""
    if len(ruc) != 11 or not ruc.isdigit():
        return f"RUC inválido: '{ruc}' — debe tener 11 dígitos"
    if not ruc.startswith(_VALID_PREFIXES):
        return f"RUC inválido: '{ruc}' — debe empezar con 10, 15, 17 o 20"
    if ruc_check_digit(ruc[:10]) != int(ruc[10]):
        return f"RUC inválido: '{ruc}' — el dígito verificador no coincide"
    return None
