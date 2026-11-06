"""Custom fields module domain — turning a spreadsheet cell into a typed value.

Imports bring every own column as cell text ("12,50", "Sí", "31/12/2026"). Stored
values must match what the product form saves: numbers as numbers, Sí/No as
true/false, dates as ``YYYY-MM-DD`` and select values as one of the field's options.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.shared.domain.errors import ValidationError

TRUE_WORDS = frozenset({"si", "s", "x", "true", "1", "verdadero", "yes"})
FALSE_WORDS = frozenset({"no", "n", "false", "0", "falso"})
_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d", "%d/%m/%y", "%d-%m-%y")
_ISO_DATETIME = re.compile(r"^(\d{4}-\d{2}-\d{2})[T ]")
_THOUSANDS_ONLY = re.compile(r"^-?\d{1,3}(,\d{3})+$")
_MAX_OPTIONS_IN_MESSAGE = 6


def _fold(text: str) -> str:
    """'  Sí ' -> 'si' (case- and accent-insensitive comparison)."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return ascii_text.strip().lower()


def _parse_decimal(raw: Any) -> Decimal | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, Decimal)):
        return Decimal(raw)
    if isinstance(raw, float):
        return Decimal(str(raw))
    text = str(raw).strip()
    text = re.sub(r"^(?:S/\.?|\$|PEN|USD)\s*", "", text, flags=re.IGNORECASE)
    text = text.replace(" ", "").replace(" ", "")
    if "," in text and "." in text:
        # The separator that comes last is the decimal one: 1,250.50 or 1.250,50.
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        # 1,250 / 12,500,000 are thousands; 12,5 is a decimal comma.
        text = text.replace(",", "") if _THOUSANDS_ONLY.match(text) else text.replace(",", ".")
    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def _json_number(number: Decimal) -> int | float:
    return int(number) if number == number.to_integral_value() else float(number)


def _parse_date(raw: Any) -> str | None:
    if isinstance(raw, datetime):
        return raw.date().isoformat()
    if isinstance(raw, date):
        return raw.isoformat()
    text = str(raw).strip()
    iso = _ISO_DATETIME.match(text)
    if iso:
        text = iso.group(1)
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def coerce_value(field_type: str, raw: Any, *, label: str, options: list[str] | None = None) -> Any:
    """The typed value of ``raw`` for a column of ``field_type``.

    Raises ValidationError («Talla: "XXL" no es una de las opciones...») when it does not fit.
    Text and URL columns keep the value as it came.
    """
    shown = str(raw).strip()
    if field_type in ("number", "currency"):
        number = _parse_decimal(raw)
        if number is None:
            what = "un monto válido" if field_type == "currency" else "un número"
            raise ValidationError(message=f"{label}: «{shown}» no es {what}.")
        if field_type == "currency":
            number = number.quantize(Decimal("0.01"))
        return _json_number(number)
    if field_type == "boolean":
        if isinstance(raw, bool):
            return raw
        word = _fold(shown)
        if word in TRUE_WORDS:
            return True
        if word in FALSE_WORDS:
            return False
        raise ValidationError(message=f"{label}: «{shown}» no se entiende. Escribe Sí o No.")
    if field_type == "date":
        parsed = _parse_date(raw)
        if parsed is None:
            raise ValidationError(message=f"{label}: «{shown}» no es una fecha válida. Usa dd/mm/aaaa.")
        return parsed
    if field_type == "select":
        choices = [o for o in (options or []) if o]
        if not choices:
            return raw
        wanted = _fold(shown)
        for option in choices:
            if _fold(option) == wanted:
                return option
        listed = ", ".join(choices[:_MAX_OPTIONS_IN_MESSAGE])
        if len(choices) > _MAX_OPTIONS_IN_MESSAGE:
            listed += "…"
        raise ValidationError(message=f"{label}: «{shown}» no es una de las opciones ({listed}).")
    return raw
