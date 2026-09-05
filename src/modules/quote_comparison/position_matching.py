from __future__ import annotations

import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from pydantic import BaseModel, Field

from src.modules.price_normalization.normalize import normalize_price, normalize_title


OfferSourceType = Literal["public_web", "commercial_quote"]
VatMode = Literal["included", "excluded", "unknown"]
RawNumeric = str | int | float | Decimal | None

_MONEY_QUANTUM = Decimal("0.01")
_MATCH_THRESHOLD = 0.30


class ProcurementPosition(BaseModel):
    position_id: str = Field(min_length=1)
    item_name: str = Field(min_length=1)
    quantity: RawNumeric = None
    unit: str | None = None
    manufacturer: str | None = None
    brand: str | None = None
    model: str | None = None
    article: str | None = None


class SupplierOfferCandidate(BaseModel):
    offer_id: str = Field(min_length=1)
    supplier_label: str = Field(min_length=1)
    supplier_id: str | None = None
    item_name: str = Field(min_length=1)
    source_type: OfferSourceType
    source_ref: str = Field(min_length=1)
    source_url: str | None = None
    currency_code: str = "RUB"
    unit_price: RawNumeric = None
    vat_mode: VatMode = "unknown"
    vat_rate: RawNumeric = None
    moq: RawNumeric = None
    delivery_time_days: int | None = None
    manufacturer: str | None = None
    brand: str | None = None
    model: str | None = None
    article: str | None = None


class NormalizedSupplierOffer(BaseModel):
    offer_id: str
    supplier_label: str
    supplier_id: str | None
    item_name: str
    source_type: OfferSourceType
    source_ref: str
    source_url: str | None
    currency_code: str
    observed_unit_price: Decimal | None
    unit_price_with_vat: Decimal | None
    unit_price_without_vat: Decimal | None
    vat_mode: VatMode
    vat_rate: Decimal | None
    moq: Decimal | None
    delivery_time_days: int | None
    manufacturer: str | None
    brand: str | None
    model: str | None
    article: str | None
    warnings: list[str] = Field(default_factory=list)


class PositionOfferMatch(BaseModel):
    position_id: str
    offer: NormalizedSupplierOffer
    match_score: float = Field(ge=0.0, le=1.0)
    eligible: bool
    match_reasons: list[str] = Field(default_factory=list)


class PositionOfferRanking(BaseModel):
    position_id: str
    best_offer_id: str | None
    matches: list[PositionOfferMatch] = Field(default_factory=list)


def _money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _normalize_identifier(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^0-9a-zа-я]+", "", value.casefold(), flags=re.IGNORECASE)


def _token_set(value: str) -> set[str]:
    return {token for token in normalize_title(value).split() if len(token) > 2}


def _title_similarity(left: str, right: str) -> float:
    left_tokens = _token_set(left)
    right_tokens = _token_set(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _equal_identifier(left: str | None, right: str | None) -> bool:
    left_value = _normalize_identifier(left)
    right_value = _normalize_identifier(right)
    return bool(left_value and right_value and left_value == right_value)


def normalize_supplier_offer(
    offer: SupplierOfferCandidate,
    *,
    required_quantity: RawNumeric = None,
) -> NormalizedSupplierOffer:
    warnings: list[str] = []
    observed_price = normalize_price(offer.unit_price)
    vat_rate = normalize_price(offer.vat_rate)

    if observed_price is None or observed_price < 0:
        observed_price = None
        warnings.append("unit_price_unknown")

    if vat_rate is not None and (vat_rate < 0 or vat_rate > 100):
        vat_rate = None
        warnings.append("vat_rate_invalid")

    price_with_vat: Decimal | None = None
    price_without_vat: Decimal | None = None
    if observed_price is not None:
        if offer.vat_mode == "included":
            price_with_vat = _money(observed_price)
            if vat_rate is not None:
                divisor = Decimal("1") + (vat_rate / Decimal("100"))
                price_without_vat = _money(observed_price / divisor)
            else:
                warnings.append("vat_rate_unknown")
        elif offer.vat_mode == "excluded":
            price_without_vat = _money(observed_price)
            if vat_rate is not None:
                multiplier = Decimal("1") + (vat_rate / Decimal("100"))
                price_with_vat = _money(observed_price * multiplier)
            else:
                warnings.append("vat_rate_unknown")
        else:
            warnings.append("vat_mode_unknown")

    moq = normalize_price(offer.moq)
    if moq is None or moq <= 0:
        moq = None
        warnings.append("moq_unknown")

    quantity = normalize_price(required_quantity)
    if moq is not None and quantity is not None and quantity > 0 and moq > quantity:
        warnings.append("moq_exceeds_required_quantity")

    delivery_time_days = offer.delivery_time_days
    if delivery_time_days is None or delivery_time_days < 0:
        delivery_time_days = None
        warnings.append("delivery_time_unknown")

    currency_code = (offer.currency_code or "RUB").strip().upper() or "RUB"
    if currency_code != "RUB":
        warnings.append("currency_not_normalized")

    return NormalizedSupplierOffer(
        offer_id=offer.offer_id,
        supplier_label=offer.supplier_label,
        supplier_id=offer.supplier_id,
        item_name=offer.item_name,
        source_type=offer.source_type,
        source_ref=offer.source_ref,
        source_url=offer.source_url,
        currency_code=currency_code,
        observed_unit_price=_money(observed_price) if observed_price is not None else None,
        unit_price_with_vat=price_with_vat,
        unit_price_without_vat=price_without_vat,
        vat_mode=offer.vat_mode,
        vat_rate=vat_rate,
        moq=moq,
        delivery_time_days=delivery_time_days,
        manufacturer=offer.manufacturer,
        brand=offer.brand,
        model=offer.model,
        article=offer.article,
        warnings=warnings,
    )


def match_offer_to_position(
    position: ProcurementPosition,
    offer: SupplierOfferCandidate,
    *,
    match_threshold: float = _MATCH_THRESHOLD,
) -> PositionOfferMatch:
    normalized_offer = normalize_supplier_offer(offer, required_quantity=position.quantity)
    reasons: list[str] = []

    position_article = _normalize_identifier(position.article)
    offer_article = _normalize_identifier(offer.article)
    if position_article and offer_article and position_article != offer_article:
        return PositionOfferMatch(
            position_id=position.position_id,
            offer=normalized_offer,
            match_score=0.0,
            eligible=False,
            match_reasons=["article_conflict"],
        )

    score = 0.0
    if position_article and offer_article and position_article == offer_article:
        score += 0.65
        reasons.append("article_match")

    if _equal_identifier(position.model, offer.model):
        score += 0.20
        reasons.append("model_match")

    brand_match = _equal_identifier(position.brand, offer.brand)
    manufacturer_match = _equal_identifier(position.manufacturer, offer.manufacturer)
    if brand_match or manufacturer_match:
        score += 0.10
        reasons.append("brand_or_manufacturer_match")

    title_similarity = _title_similarity(position.item_name, offer.item_name)
    score += title_similarity * 0.35
    reasons.append(f"title_similarity:{title_similarity:.2f}")

    score = min(score, 1.0)
    return PositionOfferMatch(
        position_id=position.position_id,
        offer=normalized_offer,
        match_score=round(score, 4),
        eligible=score >= match_threshold,
        match_reasons=reasons,
    )


def rank_offers_for_position(
    position: ProcurementPosition,
    offers: list[SupplierOfferCandidate],
    *,
    match_threshold: float = _MATCH_THRESHOLD,
) -> PositionOfferRanking:
    matches = [
        match_offer_to_position(position, offer, match_threshold=match_threshold)
        for offer in offers
    ]
    matches.sort(key=lambda match: (-match.match_score, match.offer.offer_id))
    best_offer_id = next(
        (match.offer.offer_id for match in matches if match.eligible),
        None,
    )
    return PositionOfferRanking(
        position_id=position.position_id,
        best_offer_id=best_offer_id,
        matches=matches,
    )
