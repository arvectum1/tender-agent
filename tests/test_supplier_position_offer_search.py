from src.modules.quote_comparison.position_matching import ProcurementPosition
from src.modules.supplier_search.position_offer_search import search_public_offers_for_position
from src.modules.supplier_search.yandex_search_client import YandexSearchResponse, YandexSearchResult


class FakeSearchClient:
    def __init__(self, response: YandexSearchResponse):
        self.response = response
        self.queries: list[tuple[str, int]] = []

    def search(self, query: str, max_results: int = 10) -> YandexSearchResponse:
        self.queries.append((query, max_results))
        return self.response


def test_public_supplier_results_become_source_attributed_offer_candidates() -> None:
    client = FakeSearchClient(
        YandexSearchResponse(
            items=[
                YandexSearchResult(
                    title="Schneider Electric — официальный поставщик",
                    url="https://supplier.example/a9f79116",
                    domain="supplier.example",
                    snippet="Автоматический выключатель Schneider Electric 16A A9F79116 в наличии",
                ),
                YandexSearchResult(
                    title="Marketplace",
                    url="https://ozon.ru/product/1",
                    domain="ozon.ru",
                    snippet="Автоматический выключатель 16A",
                ),
            ]
        )
    )
    position = ProcurementPosition(
        position_id="pos-1",
        item_name="Автоматический выключатель Schneider Electric 16A",
        quantity=4,
        brand="Schneider Electric",
        article="A9F79116",
    )

    outcome = search_public_offers_for_position(client, position, max_results=7)

    assert outcome.error is None
    assert client.queries and client.queries[0][1] == 7
    assert len(outcome.candidates) == 1
    candidate = outcome.candidates[0]
    assert candidate.source_type == "public_web"
    assert candidate.source_ref == "https://supplier.example/a9f79116"
    assert candidate.source_url == "https://supplier.example/a9f79116"
    assert candidate.supplier_label.startswith("Schneider Electric")
    assert candidate.unit_price is None
    assert candidate.vat_mode == "unknown"
    assert candidate.moq is None
    assert candidate.delivery_time_days is None

    assert outcome.ranking is not None
    match = outcome.ranking.matches[0]
    assert match.offer.source_ref == candidate.source_ref
    assert set(match.offer.warnings) >= {
        "unit_price_unknown",
        "moq_unknown",
        "delivery_time_unknown",
    }


def test_search_error_is_propagated_without_fabricating_candidates() -> None:
    client = FakeSearchClient(YandexSearchResponse(error="search unavailable"))
    position = ProcurementPosition(position_id="pos-2", item_name="Кабель ВВГнг 3x2.5")

    outcome = search_public_offers_for_position(client, position)

    assert outcome.error == "search unavailable"
    assert outcome.candidates == []
    assert outcome.ranking is None


def test_candidate_ids_are_deterministic_for_position_and_source() -> None:
    result = YandexSearchResult(
        title="Поставщик кабеля",
        url="https://supplier.example/cable-vvg",
        domain="supplier.example",
        snippet="Кабель ВВГнг 3x2.5 со склада",
    )
    client = FakeSearchClient(YandexSearchResponse(items=[result]))
    position = ProcurementPosition(position_id="pos-3", item_name="Кабель ВВГнг 3x2.5")

    first = search_public_offers_for_position(client, position)
    second = search_public_offers_for_position(client, position)

    assert first.candidates[0].offer_id == second.candidates[0].offer_id
    assert first.candidates[0].offer_id.startswith("public-")
