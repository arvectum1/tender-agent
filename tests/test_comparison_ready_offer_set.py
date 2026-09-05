from decimal import Decimal

from src.modules.quote_comparison.comparison_ready_offer_set import (
    ComparisonReadyOffer,
    adapt_formal_quote,
    adapt_public_offer,
    build_comparison_ready_offer_set,
)
from src.modules.quote_comparison.models import QuoteComparisonRecommendation
from src.modules.quote_comparison.position_matching import (
    ProcurementPosition,
    SupplierOfferCandidate,
    match_offer_to_position,
    rank_offers_for_position,
)
from src.modules.quote_repository.models import QuoteArtifactBinding, QuoteRecord
from src.modules.supplier_search.product_page_enrichment import (
    enrich_candidate_from_product_page,
)


def _position() -> ProcurementPosition:
    return ProcurementPosition(
        position_id="position-1",
        item_name="Контактор КМИ-22510",
        quantity=2,
        article="KMI-22510",
    )


def _public_candidate(
    *, offer_id: str = "public-1", price: Decimal | None = Decimal(1200)
) -> SupplierOfferCandidate:
    return SupplierOfferCandidate(
        offer_id=offer_id,
        supplier_label="Public Supplier",
        item_name="Контактор КМИ-22510",
        source_type="public_web",
        source_ref=f"https://public.example/{offer_id}",
        source_url=f"https://public.example/{offer_id}",
        unit_price=price,
        article="KMI-22510",
    )


def _public_match(*, offer_id: str = "public-1", price: Decimal | None = Decimal(1200)):
    return match_offer_to_position(
        _position(), _public_candidate(offer_id=offer_id, price=price)
    )


def _quote(*, quote_id: str = "QUOTE-1") -> QuoteRecord:
    return QuoteRecord(
        quote_id=quote_id,
        quote_set_id="QSET-1",
        supplier_id="SUP-1",
        rfq_id="RFQ-1",
        supplier_thread_id="THREAD-1",
        quote_status="received",
        quoted_amount=2400.0,
        currency_code="RUB",
    )


def _formal_offer(*, quote_id: str = "QUOTE-1") -> ComparisonReadyOffer:
    quote = _quote(quote_id=quote_id)
    return adapt_formal_quote(
        "position-1",
        quote,
        [QuoteArtifactBinding(quote_id=quote.quote_id, artifact_ref=f"ART-{quote_id}")],
        supplier_label="Formal Supplier",
    )


def _recommendation(*, quote_id: str = "QUOTE-1") -> QuoteComparisonRecommendation:
    return QuoteComparisonRecommendation(
        quote_comparison_set_id="M021-1",
        recommended_quote_id=quote_id,
        recommended_supplier_id="SUP-1",
        rationale="Existing M-021 recommendation.",
    )


def test_public_only_is_research_context_not_a_formal_winner() -> None:
    ranking = rank_offers_for_position(_position(), [_public_candidate()])
    offer_set = build_comparison_ready_offer_set(
        "position-1",
        public_offers=[adapt_public_offer(ranking.matches[0])],
        best_public_offer_id=ranking.best_offer_id,
    )

    assert offer_set.best_public_offer_id == "public-1"
    assert offer_set.offers[0].source_type == "public_web"
    assert offer_set.offers[0].is_public_candidate is True
    assert offer_set.offers[0].is_formal_quote is False
    assert offer_set.offers[0].comparison_ready is True
    assert offer_set.formal_recommendation.status == "not_ready"
    assert offer_set.formal_recommendation.recommended_supplier_id is None
    assert offer_set.selected_supplier_id is None


def test_quote_only_preserves_formal_quote_and_existing_m021_recommendation() -> None:
    offer_set = build_comparison_ready_offer_set(
        "position-1",
        formal_offers=[_formal_offer()],
        recommendation=_recommendation(),
    )

    offer = offer_set.offers[0]
    assert offer.offer_id == "QUOTE-1"
    assert offer.source_type == "commercial_quote"
    assert offer.is_formal_quote is True
    assert offer.is_public_candidate is False
    assert offer.quoted_amount == Decimal("2400.0")
    assert offer.quote_status == "received"
    assert offer.artifact_refs == ["ART-QUOTE-1"]
    assert offer_set.formal_recommendation.status == "available"
    assert offer_set.formal_recommendation.recommended_supplier_id == "SUP-1"
    assert offer_set.selected_supplier_id is None


def test_mixed_sources_coexist_with_distinct_provenance() -> None:
    offer_set = build_comparison_ready_offer_set(
        "position-1",
        public_offers=[adapt_public_offer(_public_match())],
        formal_offers=[_formal_offer()],
    )

    assert [offer.source_type for offer in offer_set.offers] == [
        "commercial_quote",
        "public_web",
    ]
    assert any(
        item.source_kind == "quote_record" for item in offer_set.offers[0].provenance
    )
    assert any(
        item.source_kind == "candidate" for item in offer_set.offers[1].provenance
    )
    assert offer_set.formal_recommendation.status == "unavailable"


def test_missing_commercial_data_stays_unknown_with_explicit_flags() -> None:
    candidate = SupplierOfferCandidate(
        offer_id="public-unknown",
        supplier_label="Public Supplier",
        item_name="Контактор КМИ-22510",
        source_type="public_web",
        source_ref="https://public.example/unknown",
        source_url="https://public.example/unknown",
        article="KMI-22510",
    )
    match = match_offer_to_position(_position(), candidate)
    enrichment = enrich_candidate_from_product_page(
        _position(),
        candidate,
        "<html><body>Уточняйте наличие и условия.</body></html>",
    )
    offer = adapt_public_offer(match, enrichment=enrichment)

    assert offer.observed_unit_price is None
    assert offer.vat_mode == "unknown"
    assert offer.moq is None
    assert offer.delivery_time_days is None
    assert offer.availability == "unknown"
    assert set(offer.unresolved_fields) >= {
        "price",
        "vat_mode",
        "vat_rate",
        "moq",
        "delivery_time_days",
        "availability",
    }


def test_conflicting_source_identity_is_not_unsafely_deduplicated() -> None:
    first = adapt_public_offer(_public_match(offer_id="same-id"))
    conflicting = first.model_copy(update={"observed_unit_price": Decimal("999.00")})

    offer_set = build_comparison_ready_offer_set(
        "position-1",
        public_offers=[first, conflicting],
    )

    assert len(offer_set.offers) == 2
    assert {offer.observed_unit_price for offer in offer_set.offers} == {
        Decimal("999.00"),
        Decimal("1200.00"),
    }


def test_merge_order_is_deterministic_for_identical_input() -> None:
    public_a = adapt_public_offer(_public_match(offer_id="public-a"))
    public_b = adapt_public_offer(_public_match(offer_id="public-b"))
    formal = _formal_offer(quote_id="QUOTE-2")

    first = build_comparison_ready_offer_set(
        "position-1", public_offers=[public_b, public_a], formal_offers=[formal]
    )
    second = build_comparison_ready_offer_set(
        "position-1", public_offers=[public_b, public_a], formal_offers=[formal]
    )

    assert [offer.offer_id for offer in first.offers] == [
        offer.offer_id for offer in second.offers
    ]
    assert [offer.offer_id for offer in first.offers] == [
        "QUOTE-2",
        "public-a",
        "public-b",
    ]


def test_public_rank_cannot_produce_recommended_supplier_id() -> None:
    ranking = rank_offers_for_position(_position(), [_public_candidate()])
    offer_set = build_comparison_ready_offer_set(
        "position-1",
        public_offers=[adapt_public_offer(ranking.matches[0])],
        best_public_offer_id=ranking.best_offer_id,
        recommendation=_recommendation(),
    )

    assert offer_set.best_public_offer_id == "public-1"
    assert offer_set.formal_recommendation.status == "not_ready"
    assert offer_set.formal_recommendation.recommended_supplier_id is None


def test_operator_api_makes_public_and_formal_recommendation_states_explicit(
    client,
) -> None:
    ranking = rank_offers_for_position(_position(), [_public_candidate()])
    response = client.post(
        "/quote-comparison/comparison-ready-offers",
        json={
            "position_id": "position-1",
            "public_matches": [
                match.model_dump(mode="json") for match in ranking.matches
            ],
            "best_public_offer_id": ranking.best_offer_id,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["offers"][0]["is_public_candidate"] is True
    assert payload["offers"][0]["is_formal_quote"] is False
    assert payload["offers"][0]["eligible"] is True
    assert payload["offers"][0]["comparison_ready"] is True
    assert payload["formal_recommendation"]["status"] == "not_ready"
    assert payload["formal_recommendation"]["recommended_supplier_id"] is None
    assert payload["selected_supplier_id"] is None
