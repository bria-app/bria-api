"""Suppliers module domain — entities."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.modules.suppliers.domain.exceptions import InvalidSupplierError

_RUC_RE = re.compile(r"^\d{11}$")
# Same limits as the database columns, so a long value gets a clear message instead of failing on save.
_MAX_LENGTHS = {
    "business_name": ("La razón social", 255),
    "contact_name": ("El nombre del contacto", 255),
    "phone": ("El teléfono", 30),
    "email": ("El correo", 255),
    "address": ("La dirección", 500),
}


@dataclass
class Supplier:
    """A supplier (proveedor) identified by its Peruvian RUC."""

    company_id: UUID
    ruc: str
    business_name: str
    contact_name: str = ""
    phone: str = ""
    email: str = ""
    address: str = ""
    is_active: bool = True
    custom_attributes: dict[str, Any] = field(default_factory=dict)
    id: UUID | None = None

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """Run on create and again before saving an edit (fields are mutable)."""
        if not self.business_name.strip():
            raise InvalidSupplierError(message="Escribe la razón social del proveedor.")
        if not _RUC_RE.match(self.ruc):
            raise InvalidSupplierError(message=f"El RUC «{self.ruc}» no es válido. Escribe sus 11 dígitos.")
        for attr, (label, limit) in _MAX_LENGTHS.items():
            if len(getattr(self, attr) or "") > limit:
                raise InvalidSupplierError(
                    message=f"{label} es muy largo (máximo {limit} caracteres).",
                    details={"field": attr},
                )

    def deactivate(self) -> None:
        self.is_active = False
