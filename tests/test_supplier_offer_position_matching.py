from decimal import Decimal

from src.modules.quote_comparison.position_matching import (
    ProcurementPosition,
    SupplierOfferCandidate,
    match_offer_to_position,
    normalize_supplier_offer,
    rank_offers_for_position,
)


def test_article_match_outranks_title_only_and_preserves_source_attribution() -> None:
    position = ProcurementPosition(
        position_id="pos-1",
        item_name="Автоматический выключатель Schneider Electric 16A",
        quantity=4,
        brand="Schneider Electric",
        article="A9F79116",
    )
    offers = [
        SupplierOfferCandidate(
            offer_id="offer-title",
            supplier_label="Поставщик Б",
            item_name="Автоматический выключатель Schneider Electric 16A",
            source_type="public_web",
            source_ref="https://supplier-b.example/catalog/16a",
            source_url="https://supplier-b.example/catalog/16a",
            unit_price="1 090,00",
            vat_mode="included",
            vat_rate=20,
        ),
        SupplierOfferCandidate(
            offer_id="offer-article",
            supplier_label="Поставщик А",
            item_name="Выключатель автоматический 16 ампер",
            source_type="commercial_quote",
            source_ref="tkp-2026-09-05.xlsx#row=7",
            unit_price=1100,
            vat_mode="included",
            vat_rate=20,
            brand="Schneider Electric",
            article="A9F-79116",
        ),
    ]

    ranking = rank_offers_for_position(position, offers)

    assert ranking.best_offer_id == "offer-article"
    assert ranking.matches[0].offer.source_type == "commercial_quote"
    assert ranking.matches[0].offer.source_ref == "tkp-2026-09-05.xlsx#row=7"
    assert "article_match" in ranking.matches[0].match_reasons
    assert ranking.matches[0].match_score > ranking.matches[1].match_score


def test_vat_and_moq_are_normalized_without_hiding_commercial_constraints() -> None:
    included = SupplierOfferCandidate(
        offer_id="offer-included",
        supplier_label="Поставщик А",
        item_name="Контактор 25А",
        source_type="commercial_quote",
        source_ref="tkp-a.xlsx#row=2",
        unit_price="1 200,00",
        vat_mode="included",
        vat_rate="20%",
        moq=10,
        delivery_time_days=5,
    )
    excluded = SupplierOfferCandidate(
        offer_id="offer-excluded",
        supplier_label="Поставщик Б",
        item_name="Контактор 25А",
        source_type="public_web",
        source_ref="https://supplier-b.example/item/25a",
        unit_price=1000,
        vat_mode="excluded",
        vat_rate=20,
        moq=1,
        delivery_time_days=3,
    )

    normalized_included = normalize_supplier_offer(included, required_quantity=5)
    normalized_excluded = normalize_supplier_offer(excluded, required_quantity=5)

    assert normalized_included.observed_unit_price == Decimal("1200.00")
    assert normalized_included.unit_price_with_vat == Decimal("1200.00")
    assert normalized_included.unit_price_without_vat == Decimal("1000.00")
    assert normalized_included.moq == Decimal("10")
    assert "moq_exceeds_required_quantity" in normalized_included.warnings

    assert normalized_excluded.unit_price_without_vat == Decimal("1000.00")
    assert normalized_excluded.unit_price_with_vat == Decimal("1200.00")
    assert "moq_exceeds_required_quantity" not in normalized_excluded.warnings


def test_conflicting_article_is_ineligible_even_when_title_is_identical() -> None:
    position = ProcurementPosition(
        position_id="pos-2",
        item_name="Реле контроля напряжения 220В",
        article="RKN-220-A",
    )
    offer = SupplierOfferCandidate(
        offer_id="offer-wrong-article",
        supplier_label="Поставщик",
        item_name="Реле контроля напряжения 220В",
        source_type="public_web",
        source_ref="https://supplier.example/rkn",
        article="RKN-220-B",
        unit_price=500,
        vat_mode="included",
        vat_rate=20,
    )

    match = match_offer_to_position(position, offer)

    assert match.eligible is False
    assert match.match_score == 0.0
    assert match.match_reasons == ["article_conflict"]


def test_unknown_commercial_fields_remain_explicit_instead_of_using_fake_defaults() -> None:
    offer = SupplierOfferCandidate(
        offer_id="offer-unknowns",
        supplier_label="Поставщик",
        item_name="Кабель силовой",
        source_type="public_web",
        source_ref="https://supplier.example/cable",
        unit_price="950",
        vat_mode="unknown",
        moq=None,
        delivery_time_days=None,
        currency_code="USD",
    )

    normalized = normalize_supplier_offer(offer, required_quantity=20)

    assert normalized.observed_unit_price == Decimal("950.00")
    assert normalized.unit_price_with_vat is None
    assert normalized.unit_price_without_vat is None
    assert normalized.moq is None
    assert normalized.delivery_time_days is None
    assert set(normalized.warnings) >= {
        "vat_mode_unknown",
        "moq_unknown",
        "delivery_time_unknown",
        "currency_not_normalized",
    }
