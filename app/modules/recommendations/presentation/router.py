"""Recommendations module — HTTP router wired to use cases.

Implemented: create, list (with pending filter), get, accept, dismiss. Automatic
generation from KPIs/forecasts is a placeholder for a later block.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from app.modules.recommendations.application.dtos import RecommendationDTO
from app.modules.forecasting.domain.repositories import (
    ForecastResultRepository,
    ForecastRunRepository,
)
from app.modules.inventory.domain.repositories import InventoryMovementRepository
from app.modules.products.domain.repositories import ProductRepository
from app.modules.recommendations.application.use_cases.generate import (
    GenerateRecommendations,
)
from app.modules.recommendations.application.use_cases.recommendation import (
    AcceptRecommendation,
    CreateRecommendation,
    DismissRecommendation,
    GetRecommendation,
    ListRecommendations,
)
from app.modules.recommendations.domain.repositories import RecommendationRepository
from app.modules.recommendations.presentation.dependencies import (
    get_movement_repository,
    get_product_repository,
    get_recommendation_repository,
    get_result_repository,
    get_run_repository,
    parse_priority,
)
from app.modules.recommendations.presentation.schemas import (
    CreateRecommendationRequest,
)
from app.shared.presentation.deps import AuthenticatedUser, require_company_access

router = APIRouter()


@router.get("", response_model=list[RecommendationDTO])
def list_recommendations(
    company_id: UUID,
    pending_only: bool = False,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: RecommendationRepository = Depends(get_recommendation_repository),
) -> list[RecommendationDTO]:
    return ListRecommendations(repo).execute(company_id, pending_only=pending_only)


@router.post("", response_model=RecommendationDTO, status_code=201)
def create_recommendation(
    company_id: UUID,
    request: CreateRecommendationRequest,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: RecommendationRepository = Depends(get_recommendation_repository),
) -> RecommendationDTO:
    return CreateRecommendation(repo).execute(
        company_id,
        product_id=request.product_id,
        recommended_quantity=request.recommended_quantity,
        priority=parse_priority(request.priority),
        reason=request.reason,
    )


@router.post("/generate", response_model=list[RecommendationDTO], status_code=201)
def generate_recommendations(
    company_id: UUID,
    _: AuthenticatedUser = Depends(require_company_access),
    recommendations: RecommendationRepository = Depends(get_recommendation_repository),
    products: ProductRepository = Depends(get_product_repository),
    runs: ForecastRunRepository = Depends(get_run_repository),
    results: ForecastResultRepository = Depends(get_result_repository),
    movements: InventoryMovementRepository = Depends(get_movement_repository),
) -> list[RecommendationDTO]:
    return GenerateRecommendations(
        products=products,
        runs=runs,
        results=results,
        movements=movements,
        recommendations=recommendations,
    ).execute(company_id)


@router.get("/{recommendation_id}", response_model=RecommendationDTO)
def get_recommendation(
    company_id: UUID,
    recommendation_id: UUID,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: RecommendationRepository = Depends(get_recommendation_repository),
) -> RecommendationDTO:
    return GetRecommendation(repo).execute(company_id, recommendation_id)


@router.post("/{recommendation_id}/accept", response_model=RecommendationDTO)
def accept_recommendation(
    company_id: UUID,
    recommendation_id: UUID,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: RecommendationRepository = Depends(get_recommendation_repository),
) -> RecommendationDTO:
    return AcceptRecommendation(repo).execute(company_id, recommendation_id)


@router.post("/{recommendation_id}/dismiss", response_model=RecommendationDTO)
def dismiss_recommendation(
    company_id: UUID,
    recommendation_id: UUID,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: RecommendationRepository = Depends(get_recommendation_repository),
) -> RecommendationDTO:
    return DismissRecommendation(repo).execute(company_id, recommendation_id)
