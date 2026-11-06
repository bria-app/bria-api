"""Custom fields module — HTTP routers.

* ``/companies/{company_id}/custom-fields`` — user-defined columns per entity.
* ``/companies/{company_id}/preferences/{key}`` — saved UI views (hidden columns...).
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.modules.custom_fields.application.use_cases import (
    CreateCustomField,
    CustomFieldDTO,
    DeleteCustomField,
    EnsureCustomFields,
    ListCustomFields,
    ReorderCustomFields,
    UpdateCustomField,
)
from app.modules.custom_fields.infrastructure.persistence.repositories import (
    SqlCustomFieldRepository,
    SqlUiPreferenceRepository,
)
from app.shared.infrastructure.database import get_db
from app.shared.presentation.deps import AuthenticatedUser, require_company_access
from app.shared.presentation.schemas import MessageResponse

router = APIRouter()
preferences_router = APIRouter()


def get_field_repository(db: Session = Depends(get_db, scope="function")) -> SqlCustomFieldRepository:
    return SqlCustomFieldRepository(db)


def get_preference_repository(db: Session = Depends(get_db, scope="function")) -> SqlUiPreferenceRepository:
    return SqlUiPreferenceRepository(db)


class CreateCustomFieldRequest(BaseModel):
    entity: str
    label: str = Field(min_length=1, max_length=120)
    field_type: str = "text"
    options: list[str] = []
    is_required: bool = False
    # Product columns: category ids it applies to (subcategories included). [] = all.
    category_ids: list[str] = []
    # Optional advanced config: {"validation": {...}, "alert": {...}}. Validated by the
    # domain (normalize_rules) so errors come back as a 422 with a Spanish message.
    rules: dict[str, Any] | None = None


class UpdateCustomFieldRequest(BaseModel):
    label: str | None = None
    options: list[str] | None = None
    is_visible: bool | None = None
    is_required: bool | None = None
    position: int | None = None
    category_ids: list[str] | None = None
    # None/missing keeps the current rules; {} clears them.
    rules: dict[str, Any] | None = None


class EnsureFieldSpec(BaseModel):
    label: str
    field_type: str = "text"
    options: list[str] = []
    category_ids: list[str] = []


class EnsureCustomFieldsRequest(BaseModel):
    entity: str
    fields: list[EnsureFieldSpec]


class ReorderRequest(BaseModel):
    entity: str
    ids: list[UUID]


class PreferenceBody(BaseModel):
    value: Any


class PreferenceResponse(BaseModel):
    key: str
    value: Any | None


@router.get("", response_model=list[CustomFieldDTO])
def list_custom_fields(
    company_id: UUID,
    entity: str | None = Query(None),
    _: AuthenticatedUser = Depends(require_company_access),
    repo: SqlCustomFieldRepository = Depends(get_field_repository),
) -> list[CustomFieldDTO]:
    return ListCustomFields(repo).execute(company_id, entity)


@router.post("", response_model=CustomFieldDTO, status_code=201)
def create_custom_field(
    company_id: UUID,
    request: CreateCustomFieldRequest,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: SqlCustomFieldRepository = Depends(get_field_repository),
) -> CustomFieldDTO:
    return CreateCustomField(repo).execute(
        company_id,
        entity=request.entity,
        label=request.label,
        field_type=request.field_type,
        options=request.options,
        is_required=request.is_required,
        category_ids=request.category_ids,
        rules=request.rules,
    )


@router.post("/ensure", response_model=list[CustomFieldDTO])
def ensure_custom_fields(
    company_id: UUID,
    request: EnsureCustomFieldsRequest,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: SqlCustomFieldRepository = Depends(get_field_repository),
) -> list[CustomFieldDTO]:
    return EnsureCustomFields(repo).execute(
        company_id, entity=request.entity, fields=[f.model_dump() for f in request.fields]
    )


@router.post("/reorder", response_model=list[CustomFieldDTO])
def reorder_custom_fields(
    company_id: UUID,
    request: ReorderRequest,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: SqlCustomFieldRepository = Depends(get_field_repository),
) -> list[CustomFieldDTO]:
    return ReorderCustomFields(repo).execute(company_id, entity=request.entity, ids=request.ids)


@router.patch("/{field_id}", response_model=CustomFieldDTO)
def update_custom_field(
    company_id: UUID,
    field_id: UUID,
    request: UpdateCustomFieldRequest,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: SqlCustomFieldRepository = Depends(get_field_repository),
) -> CustomFieldDTO:
    return UpdateCustomField(repo).execute(company_id, field_id, **request.model_dump())


@router.delete("/{field_id}", response_model=MessageResponse)
def delete_custom_field(
    company_id: UUID,
    field_id: UUID,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: SqlCustomFieldRepository = Depends(get_field_repository),
) -> MessageResponse:
    DeleteCustomField(repo).execute(company_id, field_id)
    return MessageResponse(message="Columna eliminada")


@preferences_router.get("/{key}", response_model=PreferenceResponse)
def get_preference(
    company_id: UUID,
    key: str,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: SqlUiPreferenceRepository = Depends(get_preference_repository),
) -> PreferenceResponse:
    return PreferenceResponse(key=key, value=repo.get(company_id, key))


@preferences_router.put("/{key}", response_model=PreferenceResponse)
def put_preference(
    company_id: UUID,
    key: str,
    body: PreferenceBody,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: SqlUiPreferenceRepository = Depends(get_preference_repository),
) -> PreferenceResponse:
    return PreferenceResponse(key=key, value=repo.put(company_id, key, body.value))
