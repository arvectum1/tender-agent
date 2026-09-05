from decimal import Decimal

from src.modules.quote_comparison.position_matching import ProcurementPosition, SupplierOfferCandidate
from src.modules.supplier_search.product_page_enrichment import (
    ProductPageFetchResult,
    ProductPageFetcher,
    enrich_candidate_from_product_page,
    enrich_public_offer_product_page,
)


def _candidate() -> SupplierOfferCandidate:
    return SupplierOfferCandidate(
        offer_id="public-web-test",
        supplier_label="Поставщик",
        item_name="Контактор 25А",
        source_type="public_web",
        source_ref="https://supplier.example/kmi-22510",
        source_url="https://supplier.example/kmi-22510",
        unit_price=Decimal("2600"),
        vat_mode="unknown",
    )


class FakeProductPageFetcher:
    def __init__(self, result: ProductPageFetchResult) -> None:
        self.result = result
        self.urls: list[str] = []

    def fetch(self, url: str) -> ProductPageFetchResult:
        self.urls.append(url)
        return self.result


def test_product_page_enrichment_replaces_terms_only_with_page_evidence() -> None:
    position = ProcurementPosition(
        position_id="pos-1",
        item_name="Контактор 25А",
        quantity=5,
        brand="IEK",
        article="KMI-22510",
    )
    html = """
    <html><head><title>IEK КМИ-22510 — контактор 25А</title></head>
    <body>
      <h1>Контактор IEK КМИ-22510 25А</h1>
      <div>Цена: 2 450 ₽ с НДС 20%</div>
      <div>Минимальная партия 3 шт.</div>
      <div>Доставка 4 дня</div>
      <div>В наличии</div>
    </body></html>
    """

    outcome = enrich_candidate_from_product_page(position, _candidate(), html)

    assert outcome.error is None
    assert outcome.candidate.unit_price == Decimal("2450")
    assert outcome.candidate.vat_mode == "included"
    assert outcome.candidate.vat_rate == Decimal("20")
    assert outcome.candidate.moq == Decimal("3")
    assert outcome.candidate.delivery_time_days == 4
    assert outcome.candidate.brand == "IEK"
    assert outcome.candidate.article == "KMI-22510"
    assert outcome.availability == "in_stock"
    assert outcome.evidence["unit_price"].source_url == _candidate().source_url
    assert "2 450 ₽" in outcome.evidence["unit_price"].evidence
    assert outcome.evidence["article"].value == "KMI-22510"


def test_product_page_does_not_invent_missing_terms_or_identifiers() -> None:
    position = ProcurementPosition(
        position_id="pos-2",
        item_name="Реле контроля напряжения",
        brand="Brand X",
        model="RX-220",
        article="RX220-A",
    )
    candidate = _candidate().model_copy(
        update={
            "unit_price": Decimal("1900"),
            "vat_mode": "excluded",
            "vat_rate": Decimal("20"),
            "moq": None,
            "delivery_time_days": None,
            "brand": None,
            "model": None,
            "article": None,
        }
    )
    html = "<html><body><h1>Реле контроля напряжения</h1><p>Позвоните, чтобы уточнить условия.</p></body></html>"

    outcome = enrich_candidate_from_product_page(position, candidate, html)

    assert outcome.error is None
    assert outcome.candidate.unit_price == Decimal("1900")
    assert outcome.candidate.vat_mode == "excluded"
    assert outcome.candidate.vat_rate == Decimal("20")
    assert outcome.candidate.brand is None
    assert outcome.candidate.model is None
    assert outcome.candidate.article is None
    assert outcome.availability == "unknown"
    assert "unit_price" not in outcome.evidence
    assert "brand" not in outcome.evidence


def test_out_of_stock_has_priority_over_generic_stock_phrase() -> None:
    position = ProcurementPosition(position_id="pos-3", item_name="Кабель")
    html = "<html><body>Товар нет в наличии. Аналоги есть в наличии.</body></html>"

    outcome = enrich_candidate_from_product_page(position, _candidate(), html)

    assert outcome.availability == "out_of_stock"
    assert outcome.evidence["availability"].value == "out_of_stock"


def test_fetch_error_is_propagated_without_changing_candidate() -> None:
    position = ProcurementPosition(position_id="pos-4", item_name="Контактор")
    candidate = _candidate()
    fetcher = FakeProductPageFetcher(
        ProductPageFetchResult(
            requested_url=candidate.source_url or "",
            error="HTTP 503",
        )
    )

    outcome = enrich_public_offer_product_page(fetcher, position, candidate)

    assert outcome.error == "HTTP 503"
    assert outcome.candidate == candidate
    assert fetcher.urls == [candidate.source_url]


def test_fetcher_rejects_private_or_non_http_urls_without_network() -> None:
    fetcher = ProductPageFetcher()

    private = fetcher.fetch("http://127.0.0.1/product")
    file_url = fetcher.fetch("file:///etc/passwd")

    assert private.error == "non-public IP addresses are not allowed"
    assert file_url.error == "only http/https URLs are allowed"
