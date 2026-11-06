"""Custom fields module domain — user-defined columns.

A company can extend its products, suppliers, purchases or sales with its own
attributes ("número de cuenta", "marca", "talla"...). The definition lives here; the
values live in each record's ``custom_attributes`` JSON, keyed by ``key``.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.shared.domain.errors import ValidationError

ENTITIES = frozenset({"product", "supplier", "purchase", "sale"})
FIELD_TYPES = frozenset({"text", "number", "currency", "date", "boolean", "select", "url"})


def slugify(label: str) -> str:
    """'Número de cuenta' -> 'numero_de_cuenta' (stable key for the JSON values)."""
    ascii_label = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_label.lower()).strip("_")
    return (slug or "campo")[:60]


def normalize_category_ids(ids: list[str] | list[UUID] | None) -> list[str]:
    """Dedupe and validate category ids, keeping the user's order."""
    out: list[str] = []
    for raw in ids or []:
        try:
            value = str(UUID(str(raw)))
        except ValueError as exc:
            raise ValidationError(message=f"Categoría inválida: {raw}") from exc
        if value not in out:
            out.append(value)
    return out


@dataclass
class CustomFieldDefinition:
    company_id: UUID
    entity: str
    label: str
    field_type: str = "text"
    key: str = ""
    options: list[str] = field(default_factory=list)
    position: int = 0
    is_visible: bool = True
    is_required: bool = False
    # Product types (category ids) the column applies to, subcategories included.
    # Empty = every record. Only meaningful for entity == "product".
    category_ids: list[str] = field(default_factory=list)
    # Optional advanced config ({"validation": {...}, "alert": {...}}), see rules.py.
    # Validated by the use cases (normalize_rules), not here: a stored rule must never
    # make loading a column fail.
    rules: dict[str, Any] = field(default_factory=dict)
    id: UUID | None = None

    def __post_init__(self) -> None:
        self.category_ids = normalize_category_ids(self.category_ids) if self.entity == "product" else []
        self.label = self.label.strip()
        if not self.label:
            raise ValidationError(message="El nombre de la columna no puede estar vacío")
        if self.entity not in ENTITIES:
            raise ValidationError(message=f"Entidad no soportada: {self.entity}")
        if self.field_type not in FIELD_TYPES:
            raise ValidationError(message=f"Tipo de columna no soportado: {self.field_type}")
        if not self.key:
            self.key = slugify(self.label)
        if self.field_type == "select":
            self.options = [o.strip() for o in self.options if o and o.strip()]
