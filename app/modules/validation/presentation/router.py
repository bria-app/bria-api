"""Validation module — HTTP router."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.modules.validation.application.use_cases.validation import (
    CreateValidationRule,
    DeleteValidationRule,
    ListValidationRules,
    UpdateValidationRule,
)
from app.modules.validation.domain.repositories import ValidationRuleRepository
from app.modules.validation.presentation.dependencies import get_validation_rule_repository
from app.modules.validation.presentation.schemas import (
    CreateValidationRuleRequest,
    UpdateValidationRuleRequest,
    ValidationResponseRequest,
    ValidationResultsResponse,
    ValidationRuleResponse,
    ValidationSessionRequest,
    ValidationSessionResponse,
)
from app.shared.presentation.deps import AuthenticatedUser, require_company_access
from app.shared.presentation.schemas import MessageResponse, PlaceholderResponse

router = APIRouter()


# --- Validation Rules Endpoints ---

@router.get("/rules", response_model=list[ValidationRuleResponse])
def list_validation_rules(
    company_id: UUID,
    repo: Annotated[ValidationRuleRepository, Depends(get_validation_rule_repository)],
    user: Annotated[AuthenticatedUser, Depends(require_company_access)],
) -> list[ValidationRuleResponse]:
    use_case = ListValidationRules(repo)
    dtos = use_case.execute(company_id=company_id)
    return [ValidationRuleResponse.model_validate(d) for d in dtos]


@router.post("/rules", response_model=ValidationRuleResponse, status_code=status.HTTP_201_CREATED)
def create_validation_rule(
    company_id: UUID,
    request: CreateValidationRuleRequest,
    repo: Annotated[ValidationRuleRepository, Depends(get_validation_rule_repository)],
    user: Annotated[AuthenticatedUser, Depends(require_company_access)],
) -> ValidationRuleResponse:
    use_case = CreateValidationRule(repo)
    dto = use_case.execute(
        company_id=company_id,
        rule_name=request.rule_name,
        rule_type=request.rule_type,
        is_active=request.is_active,
    )
    return ValidationRuleResponse.model_validate(dto)


@router.patch("/rules/{rule_id}", response_model=ValidationRuleResponse)
def update_validation_rule(
    company_id: UUID,
    rule_id: UUID,
    request: UpdateValidationRuleRequest,
    repo: Annotated[ValidationRuleRepository, Depends(get_validation_rule_repository)],
    user: Annotated[AuthenticatedUser, Depends(require_company_access)],
) -> ValidationRuleResponse:
    use_case = UpdateValidationRule(repo)
    dto = use_case.execute(
        company_id=company_id,
        rule_id=rule_id,
        rule_name=request.rule_name,
        rule_type=request.rule_type,
        is_active=request.is_active,
    )
    return ValidationRuleResponse.model_validate(dto)


@router.delete("/rules/{rule_id}", response_model=MessageResponse)
def delete_validation_rule(
    company_id: UUID,
    rule_id: UUID,
    repo: Annotated[ValidationRuleRepository, Depends(get_validation_rule_repository)],
    user: Annotated[AuthenticatedUser, Depends(require_company_access)],
) -> MessageResponse:
    use_case = DeleteValidationRule(repo)
    use_case.execute(company_id=company_id, rule_id=rule_id)
    return MessageResponse(message="Validation rule deleted successfully")


# --- Placeholder Endpoints ---

@router.get("/sessions", response_model=PlaceholderResponse)
def list_validation_sessions(company_id: UUID) -> PlaceholderResponse:
    return PlaceholderResponse(message="Endpoint scaffold ready", module="validation", action="list_validation_sessions")

@router.post("/sessions", response_model=ValidationSessionResponse)
def create_validation_session(company_id: UUID, request: ValidationSessionRequest) -> ValidationSessionResponse:
    return ValidationSessionResponse(message="Endpoint scaffold ready", module="validation", action="create_validation_session")

@router.get("/results", response_model=ValidationResultsResponse)
def get_validation_results(company_id: UUID) -> ValidationResultsResponse:
    return ValidationResultsResponse(message="Endpoint scaffold ready", module="validation", action="get_validation_results")

@router.get("/acceptance-rate", response_model=PlaceholderResponse)
def get_acceptance_rate(company_id: UUID) -> PlaceholderResponse:
    return PlaceholderResponse(message="Endpoint scaffold ready", module="validation", action="get_acceptance_rate")

@router.get("/export", response_model=PlaceholderResponse)
def export_validation(company_id: UUID) -> PlaceholderResponse:
    return PlaceholderResponse(message="Endpoint scaffold ready", module="validation", action="export_validation")

@router.get("/sessions/{session_id}", response_model=ValidationSessionResponse)
def get_validation_session(company_id: UUID, session_id: UUID) -> ValidationSessionResponse:
    return ValidationSessionResponse(message="Endpoint scaffold ready", module="validation", action="get_validation_session")

@router.patch("/sessions/{session_id}", response_model=ValidationSessionResponse)
def update_validation_session(company_id: UUID, session_id: UUID) -> ValidationSessionResponse:
    return ValidationSessionResponse(message="Endpoint scaffold ready", module="validation", action="update_validation_session")

@router.delete("/sessions/{session_id}", response_model=PlaceholderResponse)
def delete_validation_session(company_id: UUID, session_id: UUID) -> PlaceholderResponse:
    return PlaceholderResponse(message="Endpoint scaffold ready", module="validation", action="delete_validation_session")

@router.post("/sessions/{session_id}/responses", response_model=PlaceholderResponse)
def create_validation_response(company_id: UUID, session_id: UUID, request: ValidationResponseRequest) -> PlaceholderResponse:
    return PlaceholderResponse(message="Endpoint scaffold ready", module="validation", action="create_validation_response")

@router.get("/sessions/{session_id}/responses", response_model=PlaceholderResponse)
def get_validation_responses(company_id: UUID, session_id: UUID) -> PlaceholderResponse:
    return PlaceholderResponse(message="Endpoint scaffold ready", module="validation", action="get_validation_responses")
