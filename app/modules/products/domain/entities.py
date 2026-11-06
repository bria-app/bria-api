"""Products module domain — entities.

Design note: unit_price < unit_cost is allowed (loss-leader pricing is a valid
business strategy). The invariant only enforces non-negative numeric fields.

Costing: `unit_cost` holds the weighted-average cost (costo promedio ponderado) and is
maintained by inbound movements; `last_cost` is the cost of the most recent receipt.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.modules.products.domain.exceptions import InvalidProductError
from app.shared.domain.value_objects import Money, Sku

# ~1.5 MB of binary image data once base64-encoded (4/3 overhead) plus the header.
MAX_IMAGE_DATA_URL_CHARS = 2_050_000
MAX_IMAGE_URL_CHARS = 2_000
MAX_BARCODE_CHARS = 64


def normalize_barcode(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip().replace(" ", "")
    if not cleaned:
        return None
    if len(cleaned) > MAX_BARCODE_CHARS:
        raise InvalidProductError(message="El código de barras no puede superar 64 caracteres.")
    return cleaned


def normalize_image_url(value: str | None) -> str | None:
    """Accept a `data:image/...;base64,` URL (≤ ~1.5 MB) or an http(s) URL; '' clears it."""
    if value is None:
        return None
    url = value.strip()
    if not url:
        return None
    if url.startswith("data:image/"):
        if ";base64," not in url[:100]:
            raise InvalidProductError(message="La imagen debe enviarse codificada en base64.")
        if len(url) > MAX_IMAGE_DATA_URL_CHARS:
            raise InvalidProductError(message="La imagen es demasiado pesada (máximo 1.5 MB).")
        return url
    if url.startswith(("http://", "https://")):
        if len(url) > MAX_IMAGE_URL_CHARS:
            raise InvalidProductError(message="El enlace de la imagen es demasiado largo.")
        return url
    raise InvalidProductError(message="Formato de imagen no soportado. Usa JPG, PNG o WEBP.")


@dataclass
class Category:
    """Product category with optional parent for tree structures."""

    company_id: UUID
    name: str
    description: str = ""
    parent_id: UUID | None = None
    id: UUID | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise InvalidProductError(message="El nombre de la categoría no puede estar vacío.")


@dataclass
class Product:
    """A product (SKU) within a company's catalog."""

    company_id: UUID
    sku: Sku
    name: str
    unit_cost: Money
    unit_price: Money
    description: str = ""
    category_id: UUID | None = None
    unit_of_measure: str = "unit"
    lead_time_days: int = 0
    safety_stock: int = 0
    reorder_point: int = 0
    is_active: bool = True
    barcode: str | None = None
    image_url: str | None = None
    custom_attributes: dict[str, Any] = field(default_factory=dict)
    last_cost: Money | None = None
    id: UUID | None = None

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise InvalidProductError(message="El nombre del producto es obligatorio.")
        if self.lead_time_days < 0:
            raise InvalidProductError(message="El tiempo de reposición no puede ser negativo.")
        if self.safety_stock < 0:
            raise InvalidProductError(message="El stock de seguridad no puede ser negativo.")
        if self.reorder_point < 0:
            raise InvalidProductError(message="El punto de reorden no puede ser negativo.")
        self.barcode = normalize_barcode(self.barcode)
        self.image_url = normalize_image_url(self.image_url)
        if self.custom_attributes is None:
            self.custom_attributes = {}
        if not isinstance(self.custom_attributes, dict):
            raise InvalidProductError(message="Los atributos personalizados deben ser un objeto.")

    def deactivate(self) -> None:
        """Mark product as inactive."""
        self.is_active = False

    def needs_reorder(self, on_hand: int) -> bool:
        """Return True when current stock is at or below the reorder point."""
        return self.is_active and on_hand <= self.reorder_point
