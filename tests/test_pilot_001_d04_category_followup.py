from src.modules.tender_operator_agent_demo.grounded_fallback_followup import (
    _strict_category,
    _title_primary_scope,
)


def test_d04_unknown_category_is_not_silently_services():
    assert _strict_category(None) == "UNKNOWN"
    assert _strict_category("mixed") == "UNKNOWN"
    assert _strict_category("software_modification") == "UNKNOWN"


def test_d04_obvious_title_primary_scope_is_explicit():
    assert _title_primary_scope({"tender_title": "Выполнение работ по ремонту кровли"}) == "works"
    assert _title_primary_scope({"tender_title": "Оказание услуг по уборке помещений"}) == "services"
    assert _title_primary_scope({"tender_title": "Поставка автоматических выключателей"}) == "goods"
    assert _title_primary_scope({"tender_title": "Комплексное техническое обслуживание"}) is None
