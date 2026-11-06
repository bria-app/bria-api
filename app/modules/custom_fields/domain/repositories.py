"""Custom fields module — repository port (adapter: SqlCustomFieldRepository)."""
from __future__ import annotations

import builtins
from typing import Protocol
from uuid import UUID

from app.modules.custom_fields.domain.entities import CustomFieldDefinition


class CustomFieldRepository(Protocol):
    def list(
        self, company_id: UUID, entity: str | None = None
    ) -> builtins.list[CustomFieldDefinition]: ...

    def get(self, field_id: UUID) -> CustomFieldDefinition | None: ...

    def get_by_key(self, company_id: UUID, entity: str, key: str) -> CustomFieldDefinition | None: ...

    def next_position(self, company_id: UUID, entity: str) -> int: ...

    def add(self, field: CustomFieldDefinition) -> CustomFieldDefinition: ...

    def update(self, field: CustomFieldDefinition) -> CustomFieldDefinition: ...

    def delete(self, field_id: UUID) -> None: ...
