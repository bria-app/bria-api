"""Custom fields module — use cases."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any
from uuid import UUID

from app.modules.custom_fields.domain.entities import (
    CustomFieldDefinition,
    normalize_category_ids,
    slugify,
)
from app.modules.custom_fields.domain.repositories import CustomFieldRepository
from app.modules.custom_fields.domain.rules import (
    check_value,
    evaluate_alert,
    lima_today,
    normalize_rules,
    public_rules,
)
from app.modules.custom_fields.domain.values import coerce_value
from app.shared.domain.errors import ConflictError, NotFoundError


@dataclass(frozen=True)
class CustomFieldDTO:
    id: UUID
    company_id: UUID
    entity: str
    key: str
    label: str
    field_type: str
    options: list[str]
    position: int
    is_visible: bool
    is_required: bool
    category_ids: list[str]
    # Always {"validation": {...}, "alert": {...} | None}; see domain/rules.py.
    rules: dict[str, Any]

    @classmethod
    def from_entity(cls, f: CustomFieldDefinition) -> "CustomFieldDTO":
        data = asdict(f)
        data["rules"] = public_rules(f.rules)
        return cls(**data)


class ListCustomFields:
    def __init__(self, repo: CustomFieldRepository) -> None:
        self._repo = repo

    def execute(self, company_id: UUID, entity: str | None) -> list[CustomFieldDTO]:
        return [CustomFieldDTO.from_entity(f) for f in self._repo.list(company_id, entity)]


class CreateCustomField:
    def __init__(self, repo: CustomFieldRepository) -> None:
        self._repo = repo

    def execute(
        self,
        company_id: UUID,
        *,
        entity: str,
        label: str,
        field_type: str = "text",
        options: list[str] | None = None,
        is_required: bool = False,
        category_ids: list[str] | None = None,
        rules: dict[str, Any] | None = None,
    ) -> CustomFieldDTO:
        field = CustomFieldDefinition(
            company_id=company_id,
            entity=entity,
            label=label,
            field_type=field_type,
            options=options or [],
            is_required=is_required,
            category_ids=category_ids or [],
        )
        field.rules = normalize_rules(
            field.field_type, rules, label=field.label, options=field.options, entity=field.entity
        )
        if self._repo.get_by_key(company_id, entity, field.key) is not None:
            raise ConflictError(message=f"Ya existe una columna llamada «{field.label}». Usa otro nombre.")
        field.position = self._repo.next_position(company_id, entity)
        return CustomFieldDTO.from_entity(self._repo.add(field))


class EnsureCustomFields:
    """Idempotent create-if-missing, used by smart imports that add columns on the fly."""

    def __init__(self, repo: CustomFieldRepository) -> None:
        self._repo = repo

    def execute(
        self, company_id: UUID, *, entity: str, fields: list[dict[str, Any]]
    ) -> list[CustomFieldDTO]:
        for spec in fields:
            label = (spec.get("label") or "").strip()
            if not label:
                continue
            if self._repo.get_by_key(company_id, entity, slugify(label)) is None:
                self._repo.add(
                    CustomFieldDefinition(
                        company_id=company_id,
                        entity=entity,
                        label=label,
                        field_type=spec.get("field_type") or "text",
                        options=spec.get("options") or [],
                        category_ids=spec.get("category_ids") or [],
                        position=self._repo.next_position(company_id, entity),
                    )
                )
        return [CustomFieldDTO.from_entity(f) for f in self._repo.list(company_id, entity)]


class UpdateCustomField:
    def __init__(self, repo: CustomFieldRepository) -> None:
        self._repo = repo

    def execute(
        self,
        company_id: UUID,
        field_id: UUID,
        *,
        label: str | None = None,
        options: list[str] | None = None,
        is_visible: bool | None = None,
        is_required: bool | None = None,
        position: int | None = None,
        category_ids: list[str] | None = None,
        rules: dict[str, Any] | None = None,
    ) -> CustomFieldDTO:
        """``rules=None`` keeps the current rules; ``{}`` clears them."""
        field = self._repo.get(field_id)
        if field is None or field.company_id != company_id:
            raise NotFoundError(message="No encontramos esa columna. Actualiza la página e inténtalo de nuevo.")
        if category_ids is not None and field.entity == "product":
            field.category_ids = normalize_category_ids(category_ids)
        if label is not None and label.strip():
            field.label = label.strip()  # key stays stable so stored values keep working
        if options is not None:
            field.options = [o.strip() for o in options if o.strip()]
        if is_visible is not None:
            field.is_visible = is_visible
        if is_required is not None:
            field.is_required = is_required
        if position is not None:
            field.position = position
        if rules is not None or options is not None:
            # New options can invalidate a select alert («...no está entre las opciones»).
            field.rules = normalize_rules(
                field.field_type,
                rules if rules is not None else field.rules,
                label=field.label,
                options=field.options,
                entity=field.entity,
            )
        return CustomFieldDTO.from_entity(self._repo.update(field))


class ReorderCustomFields:
    def __init__(self, repo: CustomFieldRepository) -> None:
        self._repo = repo

    def execute(self, company_id: UUID, *, entity: str, ids: list[UUID]) -> list[CustomFieldDTO]:
        order = {fid: i for i, fid in enumerate(ids)}
        for field in self._repo.list(company_id, entity):
            if field.id in order:
                field.position = order[field.id]
                self._repo.update(field)
        return [CustomFieldDTO.from_entity(f) for f in self._repo.list(company_id, entity)]


class DeleteCustomField:
    def __init__(self, repo: CustomFieldRepository) -> None:
        self._repo = repo

    def execute(self, company_id: UUID, field_id: UUID) -> None:
        field = self._repo.get(field_id)
        if field is None or field.company_id != company_id:
            raise NotFoundError(message="No encontramos esa columna. Actualiza la página e inténtalo de nuevo.")
        self._repo.delete(field_id)


class CastCustomAttributes:
    """Typed, validated values for a record's own columns (imports bring cell text).

    Each value is cast to its column type and then checked against the column's
    validation rules. With ``previous`` (the record's stored values), a value equal to
    the stored one is kept untouched: existing data keeps working even when a rule was
    added later. Keys without a definition are kept as they came. The definitions are
    read once per company and entity, so one instance can cast every row of a file.
    """

    def __init__(self, repo: CustomFieldRepository) -> None:
        self._repo = repo
        self._fields: dict[tuple[UUID, str], dict[str, CustomFieldDefinition]] = {}

    def _definitions(self, company_id: UUID, entity: str) -> dict[str, CustomFieldDefinition]:
        cache_key = (company_id, entity)
        if cache_key not in self._fields:
            self._fields[cache_key] = {f.key: f for f in self._repo.list(company_id, entity)}
        return self._fields[cache_key]

    def execute(
        self,
        company_id: UUID,
        entity: str,
        attributes: dict[str, Any],
        *,
        previous: dict[str, Any] | None = None,
        today: date | None = None,
    ) -> dict[str, Any]:
        fields = self._definitions(company_id, entity)
        stored = previous or {}
        day = today or lima_today()
        typed: dict[str, Any] = {}
        for key, raw in attributes.items():
            field = fields.get(key)
            if field is None or raw is None or (isinstance(raw, str) and not raw.strip()):
                typed[key] = raw
                continue
            if key in stored and stored[key] == raw:
                typed[key] = raw  # unchanged: never re-cast nor re-validated
                continue
            value = coerce_value(field.field_type, raw, label=field.label, options=field.options)
            if not (key in stored and stored[key] == value):
                check_value(field.field_type, field.rules, value, label=field.label, today=day)
            typed[key] = value
        return typed


@dataclass(frozen=True)
class AlertHit:
    key: str
    column: str
    label: str
    tone: str


class EvaluateColumnAlerts:
    """The alerts a company's own columns raise for each record.

    ``records`` are ``(category_scope, attributes)`` pairs, where ``category_scope`` is
    the record's category id plus every ancestor id (empty when it has none): a column
    scoped to some categories only alerts records inside them. Columns are read once
    per instance, so one call serves a whole product list.
    """

    def __init__(self, repo: CustomFieldRepository) -> None:
        self._repo = repo
        self._fields: dict[tuple[UUID, str], list[CustomFieldDefinition]] = {}

    def alerting_fields(self, company_id: UUID, entity: str = "product") -> list[CustomFieldDefinition]:
        cache_key = (company_id, entity)
        if cache_key not in self._fields:
            self._fields[cache_key] = [
                f for f in self._repo.list(company_id, entity)
                if isinstance(f.rules, dict) and isinstance(f.rules.get("alert"), dict)
            ]
        return self._fields[cache_key]

    def execute(
        self,
        company_id: UUID,
        records: Iterable[tuple[set[str], dict[str, Any]]],
        *,
        entity: str = "product",
        today: date | None = None,
    ) -> list[list[AlertHit]]:
        fields = self.alerting_fields(company_id, entity)
        day = today or lima_today()
        out: list[list[AlertHit]] = []
        for scope, attributes in records:
            hits: list[AlertHit] = []
            for f in fields:
                if f.category_ids and not scope.intersection(f.category_ids):
                    continue
                hit = evaluate_alert(f.field_type, f.rules, (attributes or {}).get(f.key), today=day)
                if hit is not None:
                    hits.append(AlertHit(key=f.key, column=f.label, label=hit["label"], tone=hit["tone"]))
            out.append(hits)
        return out
