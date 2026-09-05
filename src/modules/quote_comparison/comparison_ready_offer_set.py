"""Read-model adapters for per-position public offers and formal quotations.

This module deliberately does not select a supplier or invoke M-021 scoring.  It
only makes the evidence classes visible together, while preserving the boundary
between public research and quotation-backed commercial comparison.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from src.modules.quote_comparison.models import QuoteComparisonRecommendation
from src.modules.quote_comparison.position_matching import (
    NormalizedSupplierOffer,
    PositionOfferMatch,
    normalize_supplier_offer,
)
from src.modules.quote_repository.models import QuoteArtifactBinding, QuoteRecord
from src.modules.supplier_search.product_page_enrichment import (
    ProductPageEnrichmentOutcome,
)

OfferAvailability = Literal["in_stock", "out_of_stock", "unknown"]
FormalRecommendationStatus = Literal["available", "not_ready", "unavailable"]


class OfferFieldProvenance(BaseModel):
    field_name: str = Field(min_length=1)
    source_kind: Literal[
        "candidate", "product_page", "quote_record", "artifact", "normalized"
    ]
    source_ref: str = Field(min_length=1)
    evidence: str | None = None


class ComparisonReadyOffer(BaseModel):
    """One evidence-preserving offer for exactly one procurement position."""

    offer_id: str = Field(min_length=1)
    position_id: str = Field(min_length=1)
    source_type: Literal["public_web", "commercial_quote"]
    source_ref: str = Field(min_length=1)
    source_url: str | None = None
    artifact_refs: list[str] = Field(default_factory=list)
    is_public_candidate: bool
    is_formal_quote: bool
    comparison_ready: bool
    supplier_id: str | None = None
    supplier_label: str | None = None
    item_name: str | None = None
    manufacturer: str | None = None
    brand: str | None = None
    model: str | None = None
    article: str | None = None
    observed_unit_price: Decimal | None = None
    quoted_amount: Decimal | None = None
    currency_code: str | None = None
    vat_mode: Literal["included", "excluded", "unknown"] = "unknown"
    vat_rate: Decimal | None = None
    moq: Decimal | None = None
    delivery_time_days: int | None = None
    availability: OfferAvailability = "unknown"
    match_score: float | None = None
    eligible: bool | None = None
    quote_status: str | None = None
    unresolved_fields: list[str] = Field(default_factory=list)
    provenance: list[OfferFieldProvenance] = Field(default_factory=list)


class FormalRecommendationHandoff(BaseModel):
    status: FormalRecommendationStatus
    reason: str
    quote_comparison_set_id: str | None = None
    recommended_quote_id: str | None = None
    recommended_supplier_id: str | None = None


class ComparisonReadyOfferSet(BaseModel):
    position_id: str = Field(min_length=1)
    offers: list[ComparisonReadyOffer] = Field(default_factory=list)
    best_public_offer_id: str | None = None
    formal_recommendation: FormalRecommendationHandoff
    selected_supplier_id: None = None


def _unknown_fields(offer: ComparisonReadyOffer) -> list[str]:
    unknown: list[str] = []
    if offer.observed_unit_price is None and offer.quoted_amount is None:
        unknown.append("price")
    if offer.currency_code is None:
        unknown.append("currency_code")
    if offer.vat_mode == "unknown":
        unknown.append("vat_mode")
    if offer.vat_rate is None:
        unknown.append("vat_rate")
    if offer.moq is None:
        unknown.append("moq")
    if offer.delivery_time_days is None:
        unknown.append("delivery_time_days")
    if offer.availability == "unknown":
        unknown.append("availability")
    return unknown


def _candidate_provenance(
    match: PositionOfferMatch,
    offer: NormalizedSupplierOffer,
) -> list[OfferFieldProvenance]:
    source_ref = offer.source_ref
    fields = [
        "supplier_label",
        "item_name",
        "manufacturer",
        "brand",
        "model",
        "article",
        "vat_mode",
        "vat_rate",
        "moq",
        "delivery_time_days",
    ]
    if offer.observed_unit_price is not None:
        fields.append("observed_unit_price")
    return [
        OfferFieldProvenance(
            field_name=field_name, source_kind="candidate", source_ref=source_ref
        )
        for field_name in fields
        if getattr(offer, field_name) is not None
    ] + [
        OfferFieldProvenance(
            field_name="match_score",
            source_kind="normalized",
            source_ref=source_ref,
            evidence="position matching result",
        ),
        OfferFieldProvenance(
            field_name="eligible",
            source_kind="normalized",
            source_ref=source_ref,
            evidence="position matching result",
        ),
    ]


def _public_currency_provenance(
    normalized: NormalizedSupplierOffer,
    enrichment: ProductPageEnrichmentOutcome | None,
) -> OfferFieldProvenance | None:
    if normalized.observed_unit_price is None:
        return None
    if enrichment is not None and (
        price_evidence := enrichment.evidence.get("unit_price")
    ):
        return OfferFieldProvenance(
            field_name="currency_code",
            source_kind="product_page",
            source_ref=price_evidence.source_url,
            evidence=price_evidence.evidence,
        )
    return OfferFieldProvenance(
        field_name="currency_code",
        source_kind="normalized",
        source_ref=normalized.source_ref,
        evidence="currency retained only with a parser-recognized public price",
    )


def adapt_public_offer(
    match: PositionOfferMatch,
    *,
    enrichment: ProductPageEnrichmentOutcome | None = None,
) -> ComparisonReadyOffer:
    """Map a public match, optionally enriched from its product page, without a TKP bridge."""
    if match.offer.source_type != "public_web":
        raise ValueError("Public offer adapter accepts only public_web matches")
    if enrichment is not None and enrichment.offer_id != match.offer.offer_id:
        raise ValueError("Product-page enrichment must belong to the matched offer")

    normalized = (
        normalize_supplier_offer(enrichment.candidate)
        if enrichment is not None
        else match.offer
    )
    availability: OfferAvailability = "unknown"
    provenance = _candidate_provenance(match, normalized)
    currency_code = (
        normalized.currency_code if normalized.observed_unit_price is not None else None
    )
    if currency_provenance := _public_currency_provenance(normalized, enrichment):
        provenance.append(currency_provenance)
    if enrichment is not None:
        availability = enrichment.availability
        for field_name, evidence in sorted(enrichment.evidence.items()):
            provenance.append(
                OfferFieldProvenance(
                    field_name=field_name,
                    source_kind="product_page",
                    source_ref=evidence.source_url,
                    evidence=evidence.evidence,
                )
            )

    offer = ComparisonReadyOffer(
        offer_id=normalized.offer_id,
        position_id=match.position_id,
        source_type="public_web",
        source_ref=normalized.source_ref,
        source_url=normalized.source_url,
        is_public_candidate=True,
        is_formal_quote=False,
        comparison_ready=match.eligible,
        supplier_id=normalized.supplier_id,
        supplier_label=normalized.supplier_label,
        item_name=normalized.item_name,
        manufacturer=normalized.manufacturer,
        brand=normalized.brand,
        model=normalized.model,
        article=normalized.article,
        observed_unit_price=normalized.observed_unit_price,
        currency_code=currency_code,
        vat_mode=normalized.vat_mode,
        vat_rate=normalized.vat_rate,
        moq=normalized.moq,
        delivery_time_days=normalized.delivery_time_days,
        availability=availability,
        match_score=match.match_score,
        eligible=match.eligible,
        provenance=provenance,
    )
    return offer.model_copy(update={"unresolved_fields": _unknown_fields(offer)})


def adapt_formal_quote(
    position_id: str,
    quote: QuoteRecord,
    artifact_bindings: list[QuoteArtifactBinding],
    *,
    supplier_label: str | None = None,
) -> ComparisonReadyOffer:
    """Map a QuoteRecord to a position explicitly supplied by the caller.

    QuoteRecord is an RFQ-level record and has no line-item mapping of its own;
    the explicit position argument prevents accidental fabricated allocation.
    """
    source_ref = f"quote:{quote.quote_id}"
    artifact_refs = sorted({binding.artifact_ref for binding in artifact_bindings})
    provenance = [
        OfferFieldProvenance(
            field_name="quote_id", source_kind="quote_record", source_ref=source_ref
        ),
        OfferFieldProvenance(
            field_name="quote_set_id", source_kind="quote_record", source_ref=source_ref
        ),
        OfferFieldProvenance(
            field_name="supplier_id", source_kind="quote_record", source_ref=source_ref
        ),
        OfferFieldProvenance(
            field_name="quoted_amount",
            source_kind="quote_record",
            source_ref=source_ref,
        ),
        OfferFieldProvenance(
            field_name="currency_code",
            source_kind="quote_record",
            source_ref=source_ref,
        ),
        OfferFieldProvenance(
            field_name="quote_status", source_kind="quote_record", source_ref=source_ref
        ),
    ] + [
        OfferFieldProvenance(
            field_name="artifact_ref", source_kind="artifact", source_ref=artifact_ref
        )
        for artifact_ref in artifact_refs
    ]
    offer = ComparisonReadyOffer(
        offer_id=quote.quote_id,
        position_id=position_id,
        source_type="commercial_quote",
        source_ref=source_ref,
        artifact_refs=artifact_refs,
        is_public_candidate=False,
        is_formal_quote=True,
        comparison_ready=True,
        supplier_id=quote.supplier_id,
        supplier_label=supplier_label,
        quoted_amount=Decimal(str(quote.quoted_amount)),
        currency_code=quote.currency_code,
        quote_status=str(quote.quote_status),
        provenance=provenance,
    )
    return offer.model_copy(update={"unresolved_fields": _unknown_fields(offer)})


def _deduplicate(offers: list[ComparisonReadyOffer]) -> list[ComparisonReadyOffer]:
    """Remove only byte-for-byte equivalent offers with the same source identity."""
    unique: list[ComparisonReadyOffer] = []
    for offer in offers:
        if any(
            offer.source_type == existing.source_type
            and offer.offer_id == existing.offer_id
            and offer.source_ref == existing.source_ref
            and offer == existing
            for existing in unique
        ):
            continue
        unique.append(offer)
    return unique


def _formal_handoff(
    formal_offers: list[ComparisonReadyOffer],
    recommendation: QuoteComparisonRecommendation | None,
) -> FormalRecommendationHandoff:
    if not formal_offers:
        return FormalRecommendationHandoff(
            status="not_ready",
            reason="No formal quotation-backed offers are present for this position.",
        )
    if recommendation is None:
        return FormalRecommendationHandoff(
            status="unavailable",
            reason="Formal quotations are present, but no M-021 recommendation was supplied.",
        )
    quote_ids = {offer.offer_id for offer in formal_offers}
    if recommendation.recommended_quote_id not in quote_ids:
        return FormalRecommendationHandoff(
            status="unavailable",
            reason="The supplied M-021 recommendation is not backed by a formal offer in this position.",
            quote_comparison_set_id=recommendation.quote_comparison_set_id,
        )
    return FormalRecommendationHandoff(
        status="available",
        reason="Existing M-021 formal recommendation is available.",
        quote_comparison_set_id=recommendation.quote_comparison_set_id,
        recommended_quote_id=recommendation.recommended_quote_id,
        recommended_supplier_id=recommendation.recommended_supplier_id,
    )


def build_comparison_ready_offer_set(
    position_id: str,
    *,
    public_offers: list[ComparisonReadyOffer] | None = None,
    formal_offers: list[ComparisonReadyOffer] | None = None,
    best_public_offer_id: str | None = None,
    recommendation: QuoteComparisonRecommendation | None = None,
) -> ComparisonReadyOfferSet:
    """Merge source-classed offers deterministically without selecting a supplier."""
    public = public_offers or []
    formal = formal_offers or []
    all_offers = public + formal
    if any(offer.position_id != position_id for offer in all_offers):
        raise ValueError("Every offer must belong to the requested position")
    if any(offer.source_type != "public_web" for offer in public):
        raise ValueError("public_offers must contain only public_web offers")
    if any(offer.source_type != "commercial_quote" for offer in formal):
        raise ValueError("formal_offers must contain only commercial_quote offers")
    if best_public_offer_id is not None:
        best_offer = next(
            (offer for offer in public if offer.offer_id == best_public_offer_id),
            None,
        )
        if best_offer is None:
            raise ValueError(
                "best_public_offer_id must reference a supplied public offer"
            )
        if best_offer.position_id != position_id:
            raise ValueError(
                "best_public_offer_id must reference the requested position"
            )
        if not best_offer.eligible:
            raise ValueError(
                "best_public_offer_id must reference an eligible public offer"
            )

    merged = _deduplicate(all_offers)
    merged.sort(
        key=lambda offer: (
            0 if offer.source_type == "commercial_quote" else 1,
            -(offer.match_score or 0.0),
            offer.offer_id,
            offer.source_ref,
        )
    )
    return ComparisonReadyOfferSet(
        position_id=position_id,
        offers=merged,
        best_public_offer_id=best_public_offer_id,
        formal_recommendation=_formal_handoff(formal, recommendation),
    )
