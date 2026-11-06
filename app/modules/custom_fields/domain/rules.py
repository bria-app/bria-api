"""Custom fields module domain — advanced rules of an own column.

A column may carry an optional ``rules`` object with two independent parts:

* ``validation`` — what a value must look like, by column type (max length, "only
  digits", integer only, min/max, decimals, no future dates...). Checked on product
  create, update and import.
* ``alert`` — one condition evaluated on the stored value that marks the record as
  needing attention («Por vencer», «Stock bajo»...), with a short label and a tone.

Stored compact (``{}`` when there are no rules); :func:`public_rules` gives the full
shape the API returns. Every function here is pure: "today" is always passed in.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone, tzinfo
from decimal import Decimal, InvalidOperation
from typing import Any, NoReturn

from app.modules.custom_fields.domain.values import (
    FALSE_WORDS,
    TRUE_WORDS,
    _fold,
    _json_number,
    _parse_date,
    _parse_decimal,
)
from app.shared.domain.errors import ValidationError

try:
    from zoneinfo import ZoneInfo

    LIMA: tzinfo = ZoneInfo("America/Lima")
except Exception:  # noqa: BLE001 — no tz database (e.g. Windows without tzdata)
    LIMA = timezone(timedelta(hours=-5), "America/Lima")

TYPE_LABEL = {
    "text": "Texto",
    "number": "Número",
    "currency": "Monto (S/)",
    "date": "Fecha",
    "boolean": "Sí / No",
    "select": "Lista de opciones",
    "url": "Enlace",
}

TEXT_ONLY = ("letters", "letters_numbers", "digits", "email")
DATE_LIMITS = ("not_future", "not_past")
TONES = ("warning", "danger")

VALIDATION_KEYS: dict[str, frozenset[str]] = {
    "text": frozenset({"max_length", "only"}),
    "url": frozenset({"max_length"}),
    "number": frozenset({"integer_only", "min", "max", "decimals"}),
    "currency": frozenset({"integer_only", "min", "max", "decimals"}),
    "date": frozenset({"date_limit"}),
    "boolean": frozenset(),
    "select": frozenset(),
}
_VALIDATION_NAMES = {
    "max_length": "Máximo de caracteres",
    "only": "Solo admite",
    "integer_only": "Solo enteros",
    "min": "Mínimo",
    "max": "Máximo",
    "decimals": "Decimales",
    "date_limit": "Límite de fecha",
}

_COMPARE_OPS = ("lt", "lte", "gt", "gte", "eq")
ALERT_OPS: dict[str, tuple[str, ...]] = {
    "number": (*_COMPARE_OPS, "empty"),
    "currency": (*_COMPARE_OPS, "empty"),
    "date": ("within_days", "past", "empty"),
    "select": ("eq", "empty"),
    "boolean": ("eq", "empty"),
    "text": ("eq", "empty"),
    "url": ("empty",),
}
_ALERT_KEYS = frozenset({"op", "value", "days", "include_past", "label", "tone"})

MAX_TEXT_LENGTH = 1000
MAX_DECIMALS = 6
MAX_CURRENCY_DECIMALS = 2
MAX_ALERT_DAYS = 3650
MAX_ALERT_LABEL = 40
MAX_ALERT_TEXT = 120

_DIGITS = re.compile(r"^[0-9]+$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s.]{2,}$")


def lima_today(now: datetime | None = None) -> date:
    """The shop's calendar day (America/Lima), not the server's UTC day."""
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(LIMA).date()


# --- helpers --------------------------------------------------------------------
def _fail(message: str) -> NoReturn:
    raise ValidationError(message=message)


def _is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _rule_int(raw: Any, low: int, high: int, message: str) -> int:
    if isinstance(raw, bool):
        _fail(message)
    number = _parse_decimal(raw) if raw is not None else None
    if number is None or number != number.to_integral_value() or not low <= number <= high:
        _fail(message)
    return int(number)


def _rule_number(raw: Any, message: str) -> int | float:
    number = _parse_decimal(raw) if raw is not None and not isinstance(raw, bool) else None
    if number is None:
        _fail(message)
    return _json_number(number)


def _rule_bool(raw: Any, message: str) -> bool:
    if isinstance(raw, bool):
        return raw
    if raw is None:
        return False
    _fail(message)


def _fmt_number(number: Decimal | int | float, currency: bool) -> str:
    value = Decimal(str(number))
    text = format(value.normalize(), "f") if value != value.to_integral_value() else str(int(value))
    return f"S/ {text}" if currency else text


def _decimal_places(number: Decimal) -> int:
    exponent = number.normalize().as_tuple().exponent
    return -exponent if isinstance(exponent, int) and exponent < 0 else 0


def _text_of(value: Any) -> str:
    # 12345.0 from a spreadsheet is the code «12345», not «12345.0».
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def _as_bool(raw: Any) -> bool | None:
    if isinstance(raw, bool):
        return raw
    word = _fold(str(raw))
    if word in TRUE_WORDS:
        return True
    if word in FALSE_WORDS:
        return False
    return None


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:] if text[1:2].islower() or len(text) == 1 else text


def _default_alert_label(op: str, label: str, value: Any) -> str:
    if op == "past":
        text = "Vencido"
    elif op == "within_days":
        text = "Por vencer"
    elif op == "empty":
        text = f"Sin {_lower_first(label)}"
    elif op in ("lt", "lte"):
        text = f"{label} bajo"
    elif op in ("gt", "gte"):
        text = f"{label} alto"
    elif isinstance(value, bool):
        text = f"{label}: {'Sí' if value else 'No'}"
    else:
        text = f"{label}: {value}"
    return text[:MAX_ALERT_LABEL]


# --- normalizing the rules themselves ----------------------------------------------
def _normalize_validation(field_type: str, raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        _fail("La validación de la columna debe ser un objeto.")
    allowed = VALIDATION_KEYS.get(field_type, frozenset())
    type_name = TYPE_LABEL.get(field_type, field_type)
    out: dict[str, Any] = {}
    for key, value in raw.items():
        if value is None or value is False or value == "":
            continue  # "off" for every option
        if key not in _VALIDATION_NAMES:
            _fail(f"Regla de validación desconocida: «{key}».")
        if key not in allowed:
            _fail(f"«{_VALIDATION_NAMES[key]}» no aplica a una columna de tipo {type_name}.")
        if key == "max_length":
            out[key] = _rule_int(
                value, 1, MAX_TEXT_LENGTH,
                f"El máximo de caracteres debe ser un número entero entre 1 y {MAX_TEXT_LENGTH}.",
            )
        elif key == "only":
            if value not in TEXT_ONLY:
                _fail("Elige qué admite la columna: letras, letras y números, solo dígitos o correo.")
            out[key] = value
        elif key == "integer_only":
            if _rule_bool(value, "«Solo enteros» debe ser verdadero o falso."):
                out[key] = True
        elif key in ("min", "max"):
            what = "mínimo" if key == "min" else "máximo"
            out[key] = _rule_number(value, f"El {what} debe ser un número.")
        elif key == "decimals":
            high = MAX_CURRENCY_DECIMALS if field_type == "currency" else MAX_DECIMALS
            out[key] = _rule_int(
                value, 0, high,
                "Un monto admite como máximo 2 decimales." if field_type == "currency"
                else f"Los decimales deben ser un número entero entre 0 y {MAX_DECIMALS}.",
            )
        elif key == "date_limit":
            if value not in DATE_LIMITS:
                _fail("Elige si la fecha no puede ser futura o no puede ser pasada.")
            out[key] = value
    if "min" in out and "max" in out and out["min"] > out["max"]:
        _fail("El mínimo no puede ser mayor que el máximo.")
    if out.get("integer_only") and "decimals" in out:
        if out["decimals"] > 0:
            _fail("Elige «solo enteros» o decimales, no ambos.")
        del out["decimals"]  # integer_only already means 0 decimals
    if out.get("integer_only"):
        for key in ("min", "max"):
            if key in out and Decimal(str(out[key])) != Decimal(str(out[key])).to_integral_value():
                what = "mínimo" if key == "min" else "máximo"
                _fail(f"Con «solo enteros», el {what} también debe ser un número entero.")
    return out


def _normalize_alert(
    field_type: str, raw: Any, *, label: str, options: list[str], entity: str
) -> dict[str, Any] | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        _fail("La alerta de la columna debe ser un objeto.")
    if entity != "product":
        _fail("Las alertas solo están disponibles en columnas de productos.")
    unknown = sorted(set(raw) - _ALERT_KEYS)
    if unknown:
        _fail(f"Dato de alerta desconocido: «{unknown[0]}».")
    op = raw.get("op")
    type_name = TYPE_LABEL.get(field_type, field_type)
    all_ops = {o for ops in ALERT_OPS.values() for o in ops}
    if op not in all_ops:
        _fail("Elige una condición para la alerta.")
    if op not in ALERT_OPS.get(field_type, ()):
        _fail(f"Esa condición de alerta no aplica a una columna de tipo {type_name}.")

    out: dict[str, Any] = {"op": op}
    value: Any = None
    if field_type in ("number", "currency") and op in _COMPARE_OPS:
        value = _rule_number(raw.get("value"), "La alerta necesita un valor numérico.")
        out["value"] = value
    elif op == "within_days":
        out["days"] = _rule_int(
            raw.get("days"), 1, MAX_ALERT_DAYS,
            f"Indica en cuántos días avisar (entre 1 y {MAX_ALERT_DAYS}).",
        )
        include_past = raw.get("include_past", True)
        out["include_past"] = _rule_bool(
            True if include_past is None else include_past,
            "«Incluir vencidos» debe ser verdadero o falso.",
        )
    elif op == "eq" and field_type == "boolean":
        value = _as_bool(raw.get("value")) if not _is_empty(raw.get("value")) else None
        if value is None:
            _fail("La alerta de una columna Sí / No debe ser Sí o No.")
        out["value"] = value
    elif op == "eq" and field_type == "select":
        wanted = raw.get("value")
        if _is_empty(wanted):
            _fail("Elige la opción que activa la alerta.")
        choices = [o for o in options if o]
        if choices:
            match = next((o for o in choices if _fold(o) == _fold(str(wanted))), None)
            if match is None:
                _fail(f"La alerta usa «{str(wanted).strip()}», que no está entre las opciones de la columna.")
            value = match
        else:
            value = str(wanted).strip()
        out["value"] = value
    elif op == "eq" and field_type == "text":
        wanted = raw.get("value")
        if _is_empty(wanted) or isinstance(wanted, (dict, list)):
            _fail("Escribe el texto que activa la alerta.")
        value = _text_of(wanted)
        if len(value) > MAX_ALERT_TEXT:
            _fail(f"El texto de la alerta puede tener hasta {MAX_ALERT_TEXT} caracteres.")
        out["value"] = value

    alert_label = raw.get("label")
    if alert_label is not None and not isinstance(alert_label, str):
        _fail("El nombre de la alerta debe ser un texto.")
    alert_label = (alert_label or "").strip()
    if len(alert_label) > MAX_ALERT_LABEL:
        _fail(f"El nombre de la alerta puede tener hasta {MAX_ALERT_LABEL} caracteres.")
    out["label"] = alert_label or _default_alert_label(op, label, value)

    tone = raw.get("tone") or "warning"
    if tone not in TONES:
        _fail("El tono de la alerta debe ser «warning» (aviso) o «danger» (urgente).")
    out["tone"] = tone
    return out


def normalize_rules(
    field_type: str,
    raw: Any,
    *,
    label: str,
    options: list[str] | None = None,
    entity: str = "product",
) -> dict[str, Any]:
    """Clean, validated rules for a column (compact: ``{}`` when there are none).

    Accepts the compact stored shape and the full public shape alike, so it is
    idempotent. Raises ValidationError with a short Spanish message on a wrong
    combination for the column type.
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        _fail("Las reglas de la columna deben ser un objeto.")
    unknown = sorted(set(raw) - {"validation", "alert"})
    if unknown:
        _fail(f"Regla desconocida: «{unknown[0]}».")
    out: dict[str, Any] = {}
    validation = _normalize_validation(field_type, raw.get("validation"))
    if validation:
        out["validation"] = validation
    alert = _normalize_alert(
        field_type, raw.get("alert"), label=label, options=list(options or []), entity=entity
    )
    if alert:
        out["alert"] = alert
    return out


def public_rules(rules: dict[str, Any] | None) -> dict[str, Any]:
    """The shape the API returns: always both keys."""
    rules = rules if isinstance(rules, dict) else {}
    validation = rules.get("validation")
    alert = rules.get("alert")
    return {
        "validation": dict(validation) if isinstance(validation, dict) else {},
        "alert": dict(alert) if isinstance(alert, dict) else None,
    }


# --- checking a value against the validation ------------------------------------------
def check_value(
    field_type: str, rules: dict[str, Any] | None, value: Any, *, label: str, today: date
) -> None:
    """Raise ValidationError («Código: solo admite dígitos (0-9)...») when an already
    typed value breaks the column's validation. Empty values are not checked here."""
    validation = (rules or {}).get("validation") if isinstance(rules, dict) else None
    if not isinstance(validation, dict) or not validation or _is_empty(value):
        return
    if field_type in ("text", "url"):
        _check_text(validation, _text_of(value), label)
    elif field_type in ("number", "currency"):
        _check_number(validation, value, label, currency=field_type == "currency")
    elif field_type == "date":
        _check_date(validation, value, label, today)


def _check_text(validation: dict[str, Any], text: str, label: str) -> None:
    max_length = validation.get("max_length")
    if isinstance(max_length, int) and len(text) > max_length:
        _fail(f"{label}: admite hasta {max_length} caracteres (tiene {len(text)}).")
    only = validation.get("only")
    if only == "letters" and not all(ch.isalpha() or ch == " " for ch in text):
        _fail(f"{label}: «{text}» no es válido, solo admite letras.")
    if only == "letters_numbers" and not all(ch.isalnum() or ch == " " for ch in text):
        _fail(f"{label}: «{text}» no es válido, solo admite letras y números.")
    if only == "digits" and not _DIGITS.match(text):
        _fail(f"{label}: «{text}» no es válido, solo admite dígitos (0-9).")
    if only == "email" and not _EMAIL.match(text):
        _fail(f"{label}: «{text}» no es un correo válido.")


def _check_number(validation: dict[str, Any], value: Any, label: str, *, currency: bool) -> None:
    number = _parse_decimal(value)
    if number is None:
        return  # the type cast already rejected non-numbers
    shown = _fmt_number(number, currency)
    if validation.get("integer_only") and number != number.to_integral_value():
        _fail(f"{label}: debe ser un número entero ({shown}).")
    decimals = validation.get("decimals")
    if isinstance(decimals, int) and _decimal_places(number) > decimals:
        if decimals == 0:
            _fail(f"{label}: no admite decimales ({shown}).")
        _fail(f"{label}: admite hasta {decimals} decimales ({shown}).")
    low = validation.get("min")
    if isinstance(low, (int, float)) and number < Decimal(str(low)):
        _fail(f"{label}: debe ser {_fmt_number(low, currency)} o más ({shown}).")
    high = validation.get("max")
    if isinstance(high, (int, float)) and number > Decimal(str(high)):
        _fail(f"{label}: debe ser {_fmt_number(high, currency)} o menos ({shown}).")


def _check_date(validation: dict[str, Any], value: Any, label: str, today: date) -> None:
    parsed = _parse_date(value)
    if parsed is None:
        return
    day = date.fromisoformat(parsed)
    shown = day.strftime("%d/%m/%Y")
    limit = validation.get("date_limit")
    if limit == "not_future" and day > today:
        _fail(f"{label}: no puede ser una fecha futura ({shown}).")
    if limit == "not_past" and day < today:
        _fail(f"{label}: no puede ser una fecha pasada ({shown}).")


# --- evaluating the alert ---------------------------------------------------------
def evaluate_alert(
    field_type: str, rules: dict[str, Any] | None, value: Any, *, today: date
) -> dict[str, str] | None:
    """``{"label", "tone"}`` when the column's alert fires for ``value``, else None.

    Defensive: malformed stored rules or values never raise, they just do not fire.
    """
    alert = rules.get("alert") if isinstance(rules, dict) else None
    if not isinstance(alert, dict):
        return None
    try:
        fired = _alert_fires(field_type, alert, value, today)
    except (ValueError, TypeError, InvalidOperation, ArithmeticError):
        return None
    if not fired:
        return None
    tone = str(alert.get("tone")) if alert.get("tone") in TONES else "warning"
    return {"label": str(alert.get("label") or "Revisar"), "tone": tone}


def _alert_fires(field_type: str, alert: dict[str, Any], value: Any, today: date) -> bool:
    op = alert.get("op")
    if op == "empty":
        return _is_empty(value)
    if _is_empty(value):
        return False
    target = alert.get("value")
    if field_type in ("number", "currency") and op in _COMPARE_OPS:
        number = _parse_decimal(value)
        if number is None or target is None or isinstance(target, bool):
            return False
        limit = Decimal(str(target))
        return {
            "lt": number < limit,
            "lte": number <= limit,
            "gt": number > limit,
            "gte": number >= limit,
            "eq": number == limit,
        }[op]
    if field_type == "date" and op in ("past", "within_days"):
        parsed = _parse_date(value)
        if parsed is None:
            return False
        day = date.fromisoformat(parsed)
        if op == "past":
            return day < today
        days = int(alert.get("days") or 0)
        if day < today:
            return bool(alert.get("include_past", True))
        return day <= today + timedelta(days=days)
    if op == "eq" and field_type == "boolean":
        return _as_bool(value) is not None and _as_bool(value) == _as_bool(target)
    if op == "eq" and field_type in ("select", "text"):
        return target is not None and _fold(_text_of(value)) == _fold(_text_of(target))
    return False
