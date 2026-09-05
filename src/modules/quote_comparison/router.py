from fastapi import APIRouter, Query, status

from src.modules.quote_comparison.comparison_ready_offer_set import (
    adapt_formal_quote,
    adapt_public_offer,
    build_comparison_ready_offer_set,
)
from src.modules.quote_comparison.schemas import (
    BuildComparisonReadyOfferSetRequest,
    BuildQuoteComparisonRequest,
    ComparisonReadyOfferSetResponse,
    QuoteComparisonRecommendationResponse,
    QuoteComparisonRowResponse,
    QuoteComparisonSetResponse,
)
from src.modules.quote_comparison.service import (
    build_quote_comparison,
    get_quote_comparison_recommendation,
    get_quote_comparison_set,
    list_quote_comparison_sets,
)
from src.modules.quote_repository.service import get_quote
from src.shared.api.dependencies import DBSession

router = APIRouter(tags=["quote-comparison"])


def _to_recommendation_response(recommendation) -> QuoteComparisonRecommendationResponse:
    return QuoteComparisonRecommendationResponse.model_validate(recommendation)


def _to_set_response(result: tuple) -> QuoteComparisonSetResponse:
    comparison_set, rows, recommendation = result
    return QuoteComparisonSetResponse(
        quote_comparison_set_id=comparison_set.quote_comparison_set_id,
        deal_id=comparison_set.deal_id,
        quote_set_id=comparison_set.quote_set_id,
        supplier_verification_set_id=comparison_set.supplier_verification_set_id,
        comparison_status=comparison_set.comparison_status,
        created_at=comparison_set.created_at,
        updated_at=comparison_set.updated_at,
        rows=[QuoteComparisonRowResponse.model_validate(item) for item in rows],
        recommendation=_to_recommendation_response(recommendation) if recommendation else None,
    )


@router.post(
    "/quote-comparison/comparison-ready-offers",
    response_model=ComparisonReadyOfferSetResponse,
)
def build_comparison_ready_offer_set_route(
    payload: BuildComparisonReadyOfferSetRequest,
    session: DBSession,
) -> ComparisonReadyOfferSetResponse:
    """Return an evidence-preserving read model; this endpoint never selects a supplier."""
    public_offers = [adapt_public_offer(match) for match in payload.public_matches]
    formal_offers = []
    for binding in payload.formal_quote_bindings:
        quote, artifacts = get_quote(session, binding.quote_id)
        formal_offers.append(
            adapt_formal_quote(
                payload.position_id,
                quote,
                artifacts,
                supplier_label=binding.supplier_label,
            )
        )

    recommendation = None
    if payload.quote_comparison_set_id:
        _comparison_set, _rows, recommendation = get_quote_comparison_set(
            session,
            payload.quote_comparison_set_id,
        )
    offer_set = build_comparison_ready_offer_set(
        payload.position_id,
        public_offers=public_offers,
        formal_offers=formal_offers,
        best_public_offer_id=payload.best_public_offer_id,
        recommendation=recommendation,
    )
    return ComparisonReadyOfferSetResponse.model_validate(offer_set.model_dump())


@router.post("/quote-comparison/build", response_model=QuoteComparisonSetResponse, status_code=status.HTTP_201_CREATED)
def build_quote_comparison_route(
    payload: BuildQuoteComparisonRequest, session: DBSession
) -> QuoteComparisonSetResponse:
    comparison_set = build_quote_comparison(session, payload)
    return _to_set_response(get_quote_comparison_set(session, comparison_set.quote_comparison_set_id))


@router.get("/quote-comparison/{quote_comparison_set_id}", response_model=QuoteComparisonSetResponse)
def get_quote_comparison_set_route(
    quote_comparison_set_id: str, session: DBSession
) -> QuoteComparisonSetResponse:
    return _to_set_response(get_quote_comparison_set(session, quote_comparison_set_id))


@router.get("/quote-comparison", response_model=list[QuoteComparisonSetResponse])
def list_quote_comparison_sets_route(
    session: DBSession, deal_id: str | None = Query(default=None)
) -> list[QuoteComparisonSetResponse]:
    return [_to_set_response(item) for item in list_quote_comparison_sets(session, deal_id=deal_id)]


@router.get(
    "/quote-comparison/recommendation/{quote_comparison_set_id}",
    response_model=QuoteComparisonRecommendationResponse,
)
def get_quote_comparison_recommendation_route(
    quote_comparison_set_id: str, session: DBSession
) -> QuoteComparisonRecommendationResponse:
    return _to_recommendation_response(get_quote_comparison_recommendation(session, quote_comparison_set_id))
