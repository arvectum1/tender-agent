from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from decimal import Decimal
from urllib.parse import urlparse

from src.modules.quote_comparison.position_matching import (
    PositionOfferRanking,
    ProcurementPosition,
    SupplierOfferCandidate,
    rank_offers_for_position,
)
from src.modules.supplier_search.yandex_search_client import YandexSearchClient, YandexSearchResult


_PRICE_RE = re.compile(
    r"(?P<value>\d{1,3}(?:[\s\u00a0]\d{3})*(?:[,.]\d{1,2})?|\d+(?:[,.]\d{1,2})?)"
    r"\s*(?:₽|руб(?:\.|лей|ля)?|RUB)",
    re.IGNORECASE,
)
_VAT_INCLUDED_RE = re.compile(r"\b(?:с\s+ндс|ндс\s+включ(?:ен|ён|ено|ена))\b", re.IGNORECASE)
_VAT_EXCLUDED_RE = re.compile(r"\b(?:без\s+ндс|ндс\s+не\s+включ(?:ен|ён|ено|ена))\b", re.IGNORECASE)
_VAT_RATE_RE = re.compile(r"\bндс\s*(?P<rate>\d{1,2}(?:[,.]\d+)?)\s*%", re.IGNORECASE)
_DELIVERY_DAYS_RE = re.compile(
    r"\b(?:срок\s+поставки|поставка|доставка)\D{0,20}(?P<days>\d{1,3})\s*(?:дн(?:я|ей|ь)?|сут(?:ок|ки)?)\b",
    re.IGNORECASE,
)
_MOQ_RE = re.compile(
    r"\b(?:минимальн(?:ая|ый)\s+(?:партия|заказ)|от)\s*[:\-]?\s*(?P<qty>\d+(?:[,.]\d+)?)\s*(?:шт\.?|ед\.?|штук)\b",
    re.IGNORECASE,
)
_MARKETPLACES = ("avito.ru", "ozon.ru", "wildberries.ru", "market.yandex.ru")
_TRANSLIT = str.maketrans(
    {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
        "ж": "zh", "з": "z", "и": "i", "й": "i", "к": "k", "л": "l", "м": "m",
        "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
        "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch",
        "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    }
)


@dataclass
class PositionOfferDiscoveryOutcome:
    position_id: str
    query_used: str
    candidates: list[SupplierOfferCandidate] = field(default_factory=list)
    ranking: PositionOfferRanking | None = None
    total_search_results: int = 0
    error: str | None = None


def _build_position_query(position: ProcurementPosition) -> str:
    parts: list[str] = []
    if position.article:
        parts.append(f'"{position.article}"')
    if position.model:
        parts.append(f'"{position.model}"')
    if position.brand:
        parts.append(position.brand)
    elif position.manufacturer:
        parts.append(position.manufacturer)
    parts.extend((position.item_name, "купить поставщик цена"))
    return " ".join(part.strip() for part in parts if part and part.strip())[:500]


def _strip_html(value: str) -> str:
    clean = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", clean).strip()


def _domain(result: YandexSearchResult) -> str:
    return (result.domain or urlparse(result.url).netloc).lower().replace("www.", "")


def _is_marketplace(domain: str) -> bool:
    return any(marketplace in domain for marketplace in _MARKETPLACES)


def _supplier_label(result: YandexSearchResult) -> str:
    title = _strip_html(result.title)
    domain = _domain(result)
    name = title.split(" — ")[0].split(" | ")[0].split(" / ")[0].strip()
    if len(name) < 3:
        name = domain.split(".")[0].capitalize() if domain else "Public web supplier"
    return name[:200]


def _extract_price(text: str) -> Decimal | None:
    match = _PRICE_RE.search(text)
    if not match:
        return None
    raw = match.group("value").replace("\u00a0", " ").replace(" ", "").replace(",", ".")
    try:
        value = Decimal(raw)
    except Exception:
        return None
    return value if value >= 0 else None


def _extract_vat(text: str) -> tuple[str, Decimal | None]:
    rate_match = _VAT_RATE_RE.search(text)
    rate: Decimal | None = None
    if rate_match:
        try:
            rate = Decimal(rate_match.group("rate").replace(",", "."))
        except Exception:
            rate = None
    if _VAT_EXCLUDED_RE.search(text):
        return "excluded", rate
    if _VAT_INCLUDED_RE.search(text):
        return "included", rate
    return "unknown", rate


def _extract_int(pattern: re.Pattern[str], text: str, group: str) -> int | None:
    match = pattern.search(text)
    if not match:
        return None
    try:
        return int(Decimal(match.group(group).replace(",", ".")))
    except Exception:
        return None


def _extract_decimal(pattern: re.Pattern[str], text: str, group: str) -> Decimal | None:
    match = pattern.search(text)
    if not match:
        return None
    try:
        value = Decimal(match.group(group).replace(",", "."))
    except Exception:
        return None
    return value if value > 0 else None


def _canonical_identifier(value: str | None) -> str:
    if not value:
        return ""
    transliterated = value.casefold().translate(_TRANSLIT)
    return re.sub(r"[^a-z0-9]+", "", transliterated)


def _identifier_if_evidenced(value: str | None, evidence_text: str) -> str | None:
    target = _canonical_identifier(value)
    evidence = _canonical_identifier(evidence_text)
    return value if target and target in evidence else None


def _candidate_id(position_id: str, url: str) -> str:
    digest = hashlib.sha256(f"{position_id}|{url}".encode("utf-8")).hexdigest()[:16]
    return f"public-web-{digest}"


def search_result_to_candidate(
    position: ProcurementPosition,
    result: YandexSearchResult,
) -> SupplierOfferCandidate:
    title = _strip_html(result.title)
    snippet = _strip_html(result.snippet)
    evidence_text = f"{title} {snippet}".strip()
    vat_mode, vat_rate = _extract_vat(evidence_text)

    return SupplierOfferCandidate(
        offer_id=_candidate_id(position.position_id, result.url),
        supplier_label=_supplier_label(result),
        item_name=title or _supplier_label(result),
        source_type="public_web",
        source_ref=result.url,
        source_url=result.url,
        currency_code="RUB",
        unit_price=_extract_price(evidence_text),
        vat_mode=vat_mode,
        vat_rate=vat_rate,
        moq=_extract_decimal(_MOQ_RE, evidence_text, "qty"),
        delivery_time_days=_extract_int(_DELIVERY_DAYS_RE, evidence_text, "days"),
        manufacturer=_identifier_if_evidenced(position.manufacturer, evidence_text),
        brand=_identifier_if_evidenced(position.brand, evidence_text),
        model=_identifier_if_evidenced(position.model, evidence_text),
        article=_identifier_if_evidenced(position.article, evidence_text),
    )


def discover_public_offers_for_position(
    client: YandexSearchClient,
    position: ProcurementPosition,
    *,
    max_results: int = 10,
    match_threshold: float = 0.30,
) -> PositionOfferDiscoveryOutcome:
    query = _build_position_query(position)
    response = client.search(query, max_results=max_results)
    if response.error:
        return PositionOfferDiscoveryOutcome(
            position_id=position.position_id,
            query_used=query,
            total_search_results=response.total,
            error=response.error,
        )

    candidates: list[SupplierOfferCandidate] = []
    seen_domains: set[str] = set()
    for item in response.items:
        domain = _domain(item)
        if not domain or domain in seen_domains or _is_marketplace(domain):
            continue
        seen_domains.add(domain)
        candidates.append(search_result_to_candidate(position, item))

    ranking = rank_offers_for_position(
        position,
        candidates,
        match_threshold=match_threshold,
    )
    return PositionOfferDiscoveryOutcome(
        position_id=position.position_id,
        query_used=query,
        candidates=candidates,
        ranking=ranking,
        total_search_results=response.total,
    )
