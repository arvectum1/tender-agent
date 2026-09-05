from decimal import Decimal

from src.modules.quote_comparison.position_matching import ProcurementPosition
from src.modules.supplier_search.position_offer_discovery import (
    discover_public_offers_for_position,
    search_result_to_candidate,
)
from src.modules.supplier_search.yandex_search_client import YandexSearchResponse, YandexSearchResult


class FakeSearchClient:
    def __init__(self, response: YandexSearchResponse) -> None:
        self.response = response
        self.queries: list[tuple[str, int]] = []

    def search(self, query: str, max_results: int = 10) -> YandexSearchResponse:
        self.queries.append((query, max_results))
        return self.response


def test_public_result_becomes_candidate_with_only_evidenced_identity_and_terms() -> None:
    position = ProcurementPosition(
        position_id="pos-1",
        item_name="Автоматический выключатель 16А",
        quantity=5,
        brand="Schneider Electric",
        model="Acti9 iC60N",
        article="A9F79116",
    )
    result = YandexSearchResult(
        title="Schneider Electric Acti9 iC60N A9F79116 — купить",
        url="https://supplier.example/a9f79116",
        domain="supplier.example",
        snippet="Цена 1 200 ₽ с НДС 20%. Минимальная партия 10 шт. Доставка 4 дня.",
    )

    candidate = search_result_to_candidate(position, result)

    assert candidate.source_type == "public_web"
    assert candidate.source_ref == result.url
    assert candidate.unit_price == Decimal("1200")
    assert candidate.vat_mode == "included"
    assert candidate.vat_rate == Decimal("20")
    assert candidate.moq == Decimal("10")
    assert candidate.delivery_time_days == 4
    assert candidate.brand == "Schneider Electric"
    assert candidate.model == "Acti9 iC60N"
    assert candidate.article == "A9F79116"


def test_public_result_does_not_copy_position_identifiers_without_search_evidence() -> None:
    position = ProcurementPosition(
        position_id="pos-2",
        item_name="Реле контроля напряжения 220В",
        brand="Brand X",
        model="RX-220",
        article="RX220-A",
    )
    result = YandexSearchResult(
        title="Реле контроля напряжения 220В — выгодная цена",
        url="https://supplier.example/relay",
        domain="supplier.example",
        snippet="В наличии. Цена 950 руб.",
    )

    candidate = search_result_to_candidate(position, result)

    assert candidate.brand is None
    assert candidate.model is None
    assert candidate.article is None


def test_discovery_builds_position_query_filters_marketplaces_and_ranks_candidates() -> None:
    position = ProcurementPosition(
        position_id="pos-3",
        item_name="Контактор 25А",
        brand="IEK",
        article="KMI-22510",
    )
    response = YandexSearchResponse(
        total=4,
        items=[
            YandexSearchResult(
                title="IEK КМИ-22510 контактор 25А",
                url="https://supplier-a.example/kmi-22510",
                domain="supplier-a.example",
                snippet="KMI-22510. Цена 2 500 руб. с НДС 20%.",
            ),
            YandexSearchResult(
                title="Контактор 25А IEK",
                url="https://supplier-b.example/kontaktor",
                domain="supplier-b.example",
                snippet="Цена 2 300 руб.",
            ),
            YandexSearchResult(
                title="Контактор 25А",
                url="https://www.ozon.ru/product/123",
                domain="www.ozon.ru",
                snippet="Маркетплейс",
            ),
            YandexSearchResult(
                title="Дубликат поставщика А",
                url="https://supplier-a.example/other",
                domain="supplier-a.example",
                snippet="Еще одна страница",
            ),
        ],
    )
    client = FakeSearchClient(response)

    outcome = discover_public_offers_for_position(client, position, max_results=7)

    assert outcome.error is None
    assert outcome.total_search_results == 4
    assert len(outcome.candidates) == 2
    assert outcome.candidates[0].article == "KMI-22510"
    assert outcome.ranking is not None
    assert outcome.ranking.best_offer_id == outcome.candidates[0].offer_id
    assert client.queries and client.queries[0][1] == 7
    assert '"KMI-22510"' in client.queries[0][0]
    assert "Контактор 25А" in client.queries[0][0]


def test_discovery_propagates_search_error_without_fabricating_candidates() -> None:
    position = ProcurementPosition(position_id="pos-4", item_name="Кабель ВВГнг 3x2.5")
    client = FakeSearchClient(YandexSearchResponse(error="provider unavailable"))

    outcome = discover_public_offers_for_position(client, position)

    assert outcome.error == "provider unavailable"
    assert outcome.candidates == []
    assert outcome.ranking is None
