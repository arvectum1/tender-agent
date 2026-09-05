from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from src.modules.quote_comparison.position_matching import (
    PositionOfferRanking,
    ProcurementPosition,
    SupplierOfferCandidate,
    rank_offers_for_position,
)
from src.modules.supplier_search.internet_supplier_search import search_suppliers
from src.modules.supplier_search.yandex_search_client import YandexSearchClient


@dataclass
class PositionOfferSearchOutcome:
    position_id: str
    query_used: str = ""
    candidates: list[SupplierOfferCandidate] = field(default_factory=list)
    ranking: PositionOfferRanking | None = None
    error: str | None = None


def _candidate_id(position_id: str, source_url: str) -> str:
    digest = hashlib.sha256(f"{position_id}\n{source_url}".encode("utf-8")).hexdigest()[:16]
    return f"public-{digest}"


def _candidate_item_name(supplier_name: str, supplier_snippet: str) -> str:
    snippet = supplier_snippet.strip()
    return snippet or supplier_name


def _supplier_result_to_candidate(
    position: ProcurementPosition,
    *,
    supplier_name: str,
    source_url: str,
    snippet: str,
) -> SupplierOfferCandidate:
    return SupplierOfferCandidate(
        offer_id=_candidate_id(position.position_id, source_url),
        supplier_label=supplier_name,
        item_name=_candidate_item_name(supplier_name, snippet),
        source_type="public_web",
        source_ref=source_url,
        source_url=source_url,
        currency_code="RUB",
        unit_price=None,
        vat_mode="unknown",
        vat_rate=None,
        moq=None,
        delivery_time_days=None,
    )


def search_public_offers_for_position(
    client: YandexSearchClient,
    position: ProcurementPosition,
    *,
    context_text: str | None = None,
    max_results: int = 10,
    match_threshold: float = 0.30,
) -> PositionOfferSearchOutcome:
    """Run M-016 public supplier search and adapt results into Supplier Engine candidates.

    Search-result text is treated only as source-backed public-web candidate text. Missing
    commercial terms remain unknown and are never inferred from the query or position.
    """
    search_outcome = search_suppliers(
        client=client,
        tender_title=position.item_name,
        notice_text=context_text or "",
        technical_spec_text="",
        max_results=max_results,
    )
    if search_outcome.error:
        return PositionOfferSearchOutcome(
            position_id=position.position_id,
            query_used=search_outcome.query_used,
            error=search_outcome.error,
        )

    candidates = [
        _supplier_result_to_candidate(
            position,
            supplier_name=supplier.name,
            source_url=supplier.source_url,
            snippet=supplier.snippet,
        )
        for supplier in search_outcome.suppliers
    ]
    ranking = rank_offers_for_position(
        position,
        candidates,
        match_threshold=match_threshold,
    )
    return PositionOfferSearchOutcome(
        position_id=position.position_id,
        query_used=search_outcome.query_used,
        candidates=candidates,
        ranking=ranking,
    )
