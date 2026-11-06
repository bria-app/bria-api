"""A pending recommendation follows the freshest forecast instead of outliving it."""
from __future__ import annotations

from uuid import uuid4

from app.modules.recommendations.domain.entities import Recommendation
from app.modules.recommendations.domain.enums import RecommendationPriority, RecommendationStatus
from app.shared.domain.value_objects import Quantity


def _pending() -> Recommendation:
    return Recommendation(
        company_id=uuid4(), product_id=uuid4(), recommended_quantity=Quantity(141),
        priority=RecommendationPriority.HIGH, reason="old forecast", id=uuid4(),
    )


def test_refresh_updates_a_pending_recommendation() -> None:
    rec = _pending()
    assert rec.refresh(Quantity(12), RecommendationPriority.MEDIUM, "new forecast")
    assert rec.recommended_quantity == Quantity(12)
    assert rec.priority == RecommendationPriority.MEDIUM
    assert not rec.refresh(Quantity(12), RecommendationPriority.MEDIUM, "new forecast")  # no change


def test_supersede_takes_it_out_of_the_pending_list() -> None:
    rec = _pending()
    rec.supersede()
    assert rec.status == RecommendationStatus.SUPERSEDED


def test_decisions_already_taken_are_never_rewritten() -> None:
    rec = _pending()
    rec.accept()
    assert not rec.refresh(Quantity(1), RecommendationPriority.LOW, "new forecast")
    rec.supersede()
    assert rec.status == RecommendationStatus.ACCEPTED
    assert rec.recommended_quantity == Quantity(141)
