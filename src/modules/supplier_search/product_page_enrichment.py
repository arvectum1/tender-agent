from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass, field
from decimal import Decimal
from html.parser import HTMLParser
from typing import Literal, Protocol
from urllib.parse import urlparse

import httpx

from src.modules.quote_comparison.position_matching import (
    ProcurementPosition,
    SupplierOfferCandidate,
)


_PRICE_RE = re.compile(
    r"(?P<value>\d{1,3}(?:[\s\u00a0]\d{3})*(?:[,.]\d{1,2})?|\d+(?:[,.]\d{1,2})?)"
    r"\s*(?P<currency>₽|руб(?:\.|лей|ля)?|RUB)(?!\w)",
    re.IGNORECASE,
)
_VAT_INCLUDED_RE = re.compile(r"\b(?:с\s+ндс|ндс\s+включ(?:ен|ён|ено|ена))\b", re.IGNORECASE)
_VAT_EXCLUDED_RE = re.compile(r"\b(?:без\s+ндс|ндс\s+не\s+включ(?:ен|ён|ено|ена))\b", re.IGNORECASE)
_VAT_RATE_RE = re.compile(r"\bндс\s*(?P<rate>\d{1,2}(?:[,.]\d+)?)\s*%", re.IGNORECASE)
_DELIVERY_DAYS_RE = re.compile(
    r"\b(?:срок\s+поставки|поставка|доставка)\D{0,24}(?P<days>\d{1,3})\s*(?:дн(?:я|ей|ь)?|сут(?:ок|ки)?)\b",
    re.IGNORECASE,
)
_MOQ_RE = re.compile(
    r"\b(?:минимальн(?:ая|ый)\s+(?:партия|заказ)|от)\s*[:\-]?\s*(?P<qty>\d+(?:[,.]\d+)?)\s*(?:шт\.?|ед\.?|штук)\b",
    re.IGNORECASE,
)
_IN_STOCK_RE = re.compile(r"\b(?:в\s+наличии|есть\s+в\s+наличии|на\s+складе)\b", re.IGNORECASE)
_OUT_OF_STOCK_RE = re.compile(r"\b(?:нет\s+в\s+наличии|не\s+в\s+наличии|под\s+заказ)\b", re.IGNORECASE)
_TRANSLIT = str.maketrans(
    {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
        "ж": "zh", "з": "z", "и": "i", "й": "i", "к": "k", "л": "l", "м": "m",
        "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
        "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch",
        "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    }
)
_ALLOWED_CONTENT_TYPES = ("text/html", "application/xhtml+xml", "text/plain")

Availability = Literal["in_stock", "out_of_stock", "unknown"]


@dataclass(frozen=True)
class ProductPageFieldEvidence:
    field_name: str
    value: str
    evidence: str
    source_url: str


@dataclass
class ProductPageFetchResult:
    requested_url: str
    final_url: str | None = None
    html: str | None = None
    status_code: int | None = None
    content_type: str | None = None
    error: str | None = None


@dataclass
class ProductPageEnrichmentOutcome:
    offer_id: str
    source_url: str
    candidate: SupplierOfferCandidate
    availability: Availability = "unknown"
    evidence: dict[str, ProductPageFieldEvidence] = field(default_factory=dict)
    error: str | None = None


class ProductPageFetchClient(Protocol):
    def fetch(self, url: str) -> ProductPageFetchResult: ...


class ProductPageFetcher:
    def __init__(
        self,
        *,
        timeout_seconds: float = 10.0,
        max_bytes: int = 1_000_000,
        max_redirects: int = 5,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._max_bytes = max_bytes
        self._max_redirects = max_redirects

    def fetch(self, url: str) -> ProductPageFetchResult:
        safety_error = _validate_public_url(url)
        if safety_error:
            return ProductPageFetchResult(requested_url=url, error=safety_error)

        try:
            with httpx.Client(
                timeout=self._timeout_seconds,
                follow_redirects=True,
                max_redirects=self._max_redirects,
                headers={"User-Agent": "ArvectumSupplierSearch/1.0"},
            ) as client:
                with client.stream("GET", url) as response:
                    final_url = str(response.url)
                    redirect_error = _validate_public_url(final_url)
                    if redirect_error:
                        return ProductPageFetchResult(
                            requested_url=url,
                            final_url=final_url,
                            status_code=response.status_code,
                            error=f"unsafe final URL: {redirect_error}",
                        )
                    if response.status_code < 200 or response.status_code >= 300:
                        return ProductPageFetchResult(
                            requested_url=url,
                            final_url=final_url,
                            status_code=response.status_code,
                            error=f"HTTP {response.status_code}",
                        )
                    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                    if content_type and content_type not in _ALLOWED_CONTENT_TYPES:
                        return ProductPageFetchResult(
                            requested_url=url,
                            final_url=final_url,
                            status_code=response.status_code,
                            content_type=content_type,
                            error=f"unsupported content type: {content_type}",
                        )

                    chunks: list[bytes] = []
                    size = 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > self._max_bytes:
                            return ProductPageFetchResult(
                                requested_url=url,
                                final_url=final_url,
                                status_code=response.status_code,
                                content_type=content_type or None,
                                error=f"product page exceeds {self._max_bytes} bytes",
                            )
                        chunks.append(chunk)
                    encoding = response.encoding or "utf-8"
                    html = b"".join(chunks).decode(encoding, errors="replace")
                    return ProductPageFetchResult(
                        requested_url=url,
                        final_url=final_url,
                        html=html,
                        status_code=response.status_code,
                        content_type=content_type or None,
                    )
        except Exception as exc:
            return ProductPageFetchResult(requested_url=url, error=f"fetch failed: {exc}")


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self._in_title = False
        self.text_parts: list[str] = []
        self.title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.casefold()
        if lowered in {"script", "style", "noscript"}:
            self._ignored_depth += 1
        if lowered == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.casefold()
        if lowered in {"script", "style", "noscript"} and self._ignored_depth:
            self._ignored_depth -= 1
        if lowered == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        normalized = re.sub(r"\s+", " ", data).strip()
        if not normalized:
            return
        self.text_parts.append(normalized)
        if self._in_title:
            self.title_parts.append(normalized)


def _validate_public_url(url: str) -> str | None:
    try:
        parsed = urlparse(url)
    except Exception:
        return "invalid URL"
    if parsed.scheme not in {"http", "https"}:
        return "only http/https URLs are allowed"
    if not parsed.hostname:
        return "URL host is missing"
    if parsed.username or parsed.password:
        return "credential-bearing URLs are not allowed"

    host = parsed.hostname.casefold().rstrip(".")
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        return "local hosts are not allowed"

    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        return None if _is_public_ip(literal) else "non-public IP addresses are not allowed"

    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)}
    except OSError as exc:
        return f"host resolution failed: {exc}"
    if not addresses:
        return "host resolution returned no addresses"
    for address in addresses:
        try:
            resolved = ipaddress.ip_address(address)
        except ValueError:
            return "host resolved to an invalid IP address"
        if not _is_public_ip(resolved):
            return "host resolves to a non-public IP address"
    return None


def _is_public_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def _page_text(html: str) -> tuple[str, str | None]:
    parser = _VisibleTextParser()
    parser.feed(html or "")
    text = re.sub(r"\s+", " ", " ".join(parser.text_parts)).strip()
    title = re.sub(r"\s+", " ", " ".join(parser.title_parts)).strip() or None
    return text, title


def _normalize_identifier(value: str | None) -> str:
    if not value:
        return ""
    transliterated = value.casefold().translate(_TRANSLIT)
    return re.sub(r"[^0-9a-z]+", "", transliterated, flags=re.IGNORECASE)


def _identifier_evidence(expected: str | None, text: str) -> str | None:
    normalized_expected = _normalize_identifier(expected)
    if not normalized_expected:
        return None
    if normalized_expected in _normalize_identifier(text):
        return _evidence_context(text, expected or "")
    return None


def _evidence_context(text: str, needle: str, *, radius: int = 80) -> str:
    if not text:
        return ""
    index = text.casefold().find(needle.casefold()) if needle else -1
    if index < 0:
        return text[: radius * 2].strip()
    start = max(0, index - radius)
    end = min(len(text), index + len(needle) + radius)
    return text[start:end].strip()


def _decimal_from_match(match: re.Match[str] | None, group: str) -> Decimal | None:
    if not match:
        return None
    raw = match.group(group).replace("\u00a0", " ").replace(" ", "").replace(",", ".")
    try:
        value = Decimal(raw)
    except Exception:
        return None
    return value if value >= 0 else None


def _availability(text: str) -> tuple[Availability, re.Match[str] | None]:
    out_match = _OUT_OF_STOCK_RE.search(text)
    if out_match:
        return "out_of_stock", out_match
    in_match = _IN_STOCK_RE.search(text)
    if in_match:
        return "in_stock", in_match
    return "unknown", None


def enrich_candidate_from_product_page(
    position: ProcurementPosition,
    candidate: SupplierOfferCandidate,
    html: str,
    *,
    source_url: str | None = None,
) -> ProductPageEnrichmentOutcome:
    page_url = source_url or candidate.source_url or candidate.source_ref
    text, title = _page_text(html)
    if not text:
        return ProductPageEnrichmentOutcome(
            offer_id=candidate.offer_id,
            source_url=page_url,
            candidate=candidate,
            error="product page contains no visible text",
        )

    updates: dict[str, object] = {}
    evidence: dict[str, ProductPageFieldEvidence] = {}

    price_match = _PRICE_RE.search(text)
    price = _decimal_from_match(price_match, "value")
    if price is not None and price_match is not None:
        updates["unit_price"] = price
        updates["currency_code"] = "RUB"
        evidence["unit_price"] = ProductPageFieldEvidence(
            field_name="unit_price",
            value=str(price),
            evidence=_evidence_context(text, price_match.group(0)),
            source_url=page_url,
        )

    vat_rate_match = _VAT_RATE_RE.search(text)
    vat_rate = _decimal_from_match(vat_rate_match, "rate")
    vat_mode: str | None = None
    vat_mode_match: re.Match[str] | None = None
    excluded_match = _VAT_EXCLUDED_RE.search(text)
    included_match = _VAT_INCLUDED_RE.search(text)
    if excluded_match:
        vat_mode, vat_mode_match = "excluded", excluded_match
    elif included_match:
        vat_mode, vat_mode_match = "included", included_match
    if vat_mode is not None and vat_mode_match is not None:
        updates["vat_mode"] = vat_mode
        evidence["vat_mode"] = ProductPageFieldEvidence(
            field_name="vat_mode",
            value=vat_mode,
            evidence=_evidence_context(text, vat_mode_match.group(0)),
            source_url=page_url,
        )
    if vat_rate is not None and vat_rate_match is not None:
        updates["vat_rate"] = vat_rate
        evidence["vat_rate"] = ProductPageFieldEvidence(
            field_name="vat_rate",
            value=str(vat_rate),
            evidence=_evidence_context(text, vat_rate_match.group(0)),
            source_url=page_url,
        )

    moq_match = _MOQ_RE.search(text)
    moq = _decimal_from_match(moq_match, "qty")
    if moq is not None and moq > 0 and moq_match is not None:
        updates["moq"] = moq
        evidence["moq"] = ProductPageFieldEvidence(
            field_name="moq",
            value=str(moq),
            evidence=_evidence_context(text, moq_match.group(0)),
            source_url=page_url,
        )

    delivery_match = _DELIVERY_DAYS_RE.search(text)
    delivery = _decimal_from_match(delivery_match, "days")
    if delivery is not None and delivery_match is not None:
        updates["delivery_time_days"] = int(delivery)
        evidence["delivery_time_days"] = ProductPageFieldEvidence(
            field_name="delivery_time_days",
            value=str(int(delivery)),
            evidence=_evidence_context(text, delivery_match.group(0)),
            source_url=page_url,
        )

    for field_name in ("manufacturer", "brand", "model", "article"):
        expected = getattr(position, field_name)
        matched_context = _identifier_evidence(expected, text)
        if expected and matched_context:
            updates[field_name] = expected
            evidence[field_name] = ProductPageFieldEvidence(
                field_name=field_name,
                value=expected,
                evidence=matched_context,
                source_url=page_url,
            )

    availability, availability_match = _availability(text)
    if availability_match is not None:
        evidence["availability"] = ProductPageFieldEvidence(
            field_name="availability",
            value=availability,
            evidence=_evidence_context(text, availability_match.group(0)),
            source_url=page_url,
        )

    if title:
        evidence["page_title"] = ProductPageFieldEvidence(
            field_name="page_title",
            value=title,
            evidence=title,
            source_url=page_url,
        )

    enriched = candidate.model_copy(update=updates)
    return ProductPageEnrichmentOutcome(
        offer_id=candidate.offer_id,
        source_url=page_url,
        candidate=enriched,
        availability=availability,
        evidence=evidence,
    )


def enrich_public_offer_product_page(
    fetcher: ProductPageFetchClient,
    position: ProcurementPosition,
    candidate: SupplierOfferCandidate,
) -> ProductPageEnrichmentOutcome:
    page_url = candidate.source_url or candidate.source_ref
    fetched = fetcher.fetch(page_url)
    effective_url = fetched.final_url or page_url
    if fetched.error or fetched.html is None:
        return ProductPageEnrichmentOutcome(
            offer_id=candidate.offer_id,
            source_url=effective_url,
            candidate=candidate,
            error=fetched.error or "product page body is unavailable",
        )
    return enrich_candidate_from_product_page(
        position,
        candidate,
        fetched.html,
        source_url=effective_url,
    )
