"""Suppliers module — use cases for the Supplier aggregate."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from app.modules.suppliers.application.dtos import (
    ImportErrorDTO,
    SupplierDTO,
    SupplierImportResultDTO,
    SupplierSummaryDTO,
)
from app.modules.suppliers.domain.entities import Supplier
from app.modules.suppliers.domain.exceptions import (
    DuplicateSupplierError,
    InvalidSupplierError,
    SupplierNotFoundError,
)
from app.modules.suppliers.domain.repositories import (
    SupplierRepository,
    SupplierStatsReader,
    UnitOfWorkSavepoint,
)
from app.modules.suppliers.domain.ruc import normalize_ruc, ruc_error
from app.shared.domain.errors import DomainError


def _clean_custom(values: dict[str, Any] | None) -> dict[str, Any]:
    """Drop empty values so blank inputs don't clutter custom_attributes."""
    return {k: v for k, v in (values or {}).items() if v is not None and v != ""}


def _validated_ruc(raw: str) -> str:
    ruc = normalize_ruc(raw)
    error = ruc_error(ruc)
    if error:
        raise InvalidSupplierError(message=error, details={"ruc": raw})
    return ruc


def _owned(repo: SupplierRepository, company_id: UUID, supplier_id: UUID) -> Supplier:
    supplier = repo.get_by_id(supplier_id)
    if supplier is None or supplier.company_id != company_id:
        raise SupplierNotFoundError(supplier_id)
    return supplier


class CreateSupplier:
    def __init__(self, suppliers: SupplierRepository) -> None:
        self._suppliers = suppliers

    def execute(
        self,
        company_id: UUID,
        *,
        ruc: str,
        business_name: str,
        contact_name: str = "",
        phone: str = "",
        email: str = "",
        address: str = "",
        custom_attributes: dict[str, Any] | None = None,
    ) -> SupplierDTO:
        clean_ruc = _validated_ruc(ruc)
        if self._suppliers.get_by_ruc(company_id, clean_ruc) is not None:
            raise DuplicateSupplierError(clean_ruc)
        supplier = Supplier(
            company_id=company_id,
            ruc=clean_ruc,
            business_name=business_name.strip(),
            contact_name=contact_name.strip(),
            phone=phone.strip(),
            email=email.strip(),
            address=address.strip(),
            custom_attributes=_clean_custom(custom_attributes),
        )
        return SupplierDTO.from_entity(self._suppliers.add(supplier))


class ListSuppliers:
    def __init__(self, suppliers: SupplierRepository, stats: SupplierStatsReader) -> None:
        self._suppliers = suppliers
        self._stats = stats

    def execute(self, company_id: UUID) -> list[SupplierDTO]:
        totals = self._stats.totals_by_supplier(company_id)
        return [
            SupplierDTO.from_entity(s, totals.get(s.id))  # type: ignore[arg-type]
            for s in self._suppliers.list_by_company(company_id)
        ]


class GetSupplier:
    def __init__(self, suppliers: SupplierRepository) -> None:
        self._suppliers = suppliers

    def execute(self, company_id: UUID, supplier_id: UUID) -> SupplierDTO:
        return SupplierDTO.from_entity(_owned(self._suppliers, company_id, supplier_id))


class GetSupplierSummary:
    def __init__(self, suppliers: SupplierRepository, stats: SupplierStatsReader) -> None:
        self._suppliers = suppliers
        self._stats = stats

    def execute(self, company_id: UUID, supplier_id: UUID) -> SupplierSummaryDTO:
        supplier = _owned(self._suppliers, company_id, supplier_id)
        data = self._stats.summary(company_id, supplier_id)
        totals = {
            "total_purchased": data["total_purchased"],
            "purchase_lines": data["purchases_count"],
            "last_purchase_date": data["last_purchase_date"],
        }
        return SupplierSummaryDTO(supplier=SupplierDTO.from_entity(supplier, totals), **data)


class UpdateSupplier:
    def __init__(self, suppliers: SupplierRepository) -> None:
        self._suppliers = suppliers

    def execute(
        self,
        company_id: UUID,
        supplier_id: UUID,
        *,
        business_name: str | None = None,
        contact_name: str | None = None,
        phone: str | None = None,
        email: str | None = None,
        address: str | None = None,
        is_active: bool | None = None,
        custom_attributes: dict[str, Any] | None = None,
    ) -> SupplierDTO:
        supplier = _owned(self._suppliers, company_id, supplier_id)
        if business_name is not None:
            if not business_name.strip():
                raise InvalidSupplierError(message="Escribe la razón social del proveedor.")
            supplier.business_name = business_name.strip()
        if contact_name is not None:
            supplier.contact_name = contact_name.strip()
        if phone is not None:
            supplier.phone = phone.strip()
        if email is not None:
            supplier.email = email.strip()
        if address is not None:
            supplier.address = address.strip()
        if is_active is not None:
            supplier.is_active = is_active
        if custom_attributes is not None:
            supplier.custom_attributes = _clean_custom(custom_attributes)
        supplier.validate()
        return SupplierDTO.from_entity(self._suppliers.update(supplier))


class DeleteSupplier:
    def __init__(self, suppliers: SupplierRepository) -> None:
        self._suppliers = suppliers

    def execute(self, company_id: UUID, supplier_id: UUID) -> bool:
        _owned(self._suppliers, company_id, supplier_id)
        self._suppliers.delete(supplier_id)
        return True


class ImportSuppliers:
    """Bulk create suppliers. A RUC that already exists updates the fields the file brings."""

    def __init__(self, suppliers: SupplierRepository, uow: UnitOfWorkSavepoint) -> None:
        self._suppliers = suppliers
        self._uow = uow

    def execute(self, company_id: UUID, rows: list[dict[str, Any]]) -> SupplierImportResultDTO:
        created = updated = skipped = 0
        errors: list[ImportErrorDTO] = []
        seen: set[str] = set()

        for index, row in enumerate(rows, start=1):
            row_no = int(row.get("row") or index)
            try:
                with self._uow.savepoint():
                    ruc = _validated_ruc(str(row.get("ruc") or ""))
                    name = str(row.get("business_name") or "").strip()
                    if ruc in seen:
                        skipped += 1
                        continue
                    seen.add(ruc)
                    fields = {
                        k: str(row.get(k) or "").strip()
                        for k in ("contact_name", "phone", "email", "address")
                    }
                    custom = _clean_custom(row.get("custom_attributes"))
                    existing = self._suppliers.get_by_ruc(company_id, ruc)
                    if existing is not None:
                        changed = False
                        if name and name != existing.business_name:
                            existing.business_name = name
                            changed = True
                        for key, value in fields.items():
                            if value and value != getattr(existing, key):
                                setattr(existing, key, value)
                                changed = True
                        merged = {**existing.custom_attributes, **custom}
                        if merged != existing.custom_attributes:
                            existing.custom_attributes = merged
                            changed = True
                        if changed:
                            existing.validate()
                            self._suppliers.update(existing)
                            updated += 1
                        else:
                            skipped += 1
                        continue
                    if not name:
                        raise InvalidSupplierError(message="Falta la razón social del proveedor.")
                    self._suppliers.add(
                        Supplier(
                            company_id=company_id,
                            ruc=ruc,
                            business_name=name,
                            contact_name=fields["contact_name"],
                            phone=fields["phone"],
                            email=fields["email"],
                            address=fields["address"],
                            custom_attributes=custom,
                        )
                    )
                    created += 1
            except DomainError as exc:
                errors.append(ImportErrorDTO(row=row_no, message=exc.message))
            except Exception as exc:  # noqa: BLE001 — report the row, keep importing
                errors.append(ImportErrorDTO(row=row_no, message=f"No se pudo guardar la fila ({type(exc).__name__}). Revisa sus datos e inténtalo de nuevo."))

        return SupplierImportResultDTO(created=created, updated=updated, skipped=skipped, errors=errors)
