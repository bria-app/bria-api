"""Data preparation — file parsing (infrastructure).

Parses ingested CSV content into RawDemandRow using the batch's column_mapping, which
maps canonical fields to the file's header names:
    {"date": "Fecha", "sku": "SKU", "quantity": "Cantidad", "stockout": "SinStock"}
The "stockout" mapping is optional. Excel is not supported yet (no openpyxl dependency).
"""
from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal, InvalidOperation

from app.modules.data_preparation.domain.value_objects import RawDemandRow
from app.modules.ingestion.domain.enums import FileType
from app.shared.domain.errors import ValidationError

_REQUIRED_FIELDS = ("date", "sku", "quantity")
_TRUTHY = {"1", "true", "yes", "si", "sí", "y", "t"}


def parse_demand_rows(
    *,
    content: bytes,
    file_type: FileType,
    column_mapping: dict[str, str],
) -> list[RawDemandRow]:
    if file_type is not FileType.CSV:
        raise ValidationError(
            message="Por ahora solo se preparan archivos CSV. Exporta tu archivo a CSV y vuelve a subirlo."
        )
    missing = [f for f in _REQUIRED_FIELDS if f not in column_mapping]
    if missing:
        raise ValidationError(
            message=f"Falta indicar qué columna es: {', '.join(missing)}. Completa el mapeo de columnas."
        )

    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    date_col = column_mapping["date"]
    sku_col = column_mapping["sku"]
    qty_col = column_mapping["quantity"]
    stockout_col = column_mapping.get("stockout")

    rows: list[RawDemandRow] = []
    for line_no, raw in enumerate(reader, start=2):  # row 1 is the header
        sku = (raw.get(sku_col) or "").strip()
        date_str = (raw.get(date_col) or "").strip()
        qty_str = (raw.get(qty_col) or "").strip()
        if not sku or not date_str:
            continue  # skip incomplete rows
        try:
            period_date = date.fromisoformat(date_str)
        except ValueError as exc:
            raise ValidationError(
                message=f"Fila {line_no}: la fecha «{date_str}» no es válida. Usa el formato AAAA-MM-DD."
            ) from exc
        try:
            quantity = Decimal(qty_str) if qty_str else Decimal("0")
        except InvalidOperation as exc:
            raise ValidationError(
                message=f"Fila {line_no}: la cantidad «{qty_str}» no es un número. Corrígela."
            ) from exc
        is_stockout = False
        if stockout_col is not None:
            is_stockout = (raw.get(stockout_col) or "").strip().lower() in _TRUTHY
        rows.append(
            RawDemandRow(
                sku=sku,
                period_date=period_date,
                quantity=quantity,
                is_stockout=is_stockout,
            )
        )
    return rows
