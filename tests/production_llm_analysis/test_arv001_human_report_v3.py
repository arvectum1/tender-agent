from __future__ import annotations

from copy import deepcopy

import pytest

from scripts.arv001 import refine_human_report_v3
from scripts.arv001.complete_corpus_contract import (
    DEFAULT_REGISTRY_NUMBER,
    AcceptanceBlocked,
)


def _v2_html() -> str:
    return f"""<!doctype html><html lang="ru"><body><main>
<section><h1>Анализ закупки № {DEFAULT_REGISTRY_NUMBER}</h1>
<p>Отчёт для принятия решения об участии</p>
<details><summary>Документы комплекта (6)</summary><ul>
<li>Извещение о закупке (извещение)</li>
<li>Приложение 1 Описание объекта закупки (техническая документация)</li>
<li>Приложение 2 Обоснование НМЦК (ценовое обоснование)</li>
<li>Приложение 3 Требования к составу заявки (требования к заявке)</li>
<li>Приложение 4 Проект контракта (проект контракта)</li>
<li>Приложение 5 Реквизиты для обеспечения исполнения контракта (обеспечение исполнения контракта)</li>
</ul></details></section>
<section class="decision"><h2>Предварительная рекомендация: HOLD — сначала вручную подтвердить актуальность срока подачи</h2>
<p><strong>Статус срока подачи:</strong> срок требует проверки.</p>
<h3>Основания</h3><ul>
<li>Техническая документация и проект контракта включены в комплект анализа.</li>
</ul><p><strong>Следующее действие:</strong> Проверить документы.</p></section>
<section><h2>Условия контракта</h2><h3>Поставка и приёмка</h3><ul>
<li>Срок приемки: 7 рабочих дней со дня подписания Заказчиком документа о приемке.</li>
</ul></section>
<section><h2>Ограничения текущего автоматического извлечения</h2><ul>
<li>Детальные характеристики товара не представлены.</li>
</ul></section>
<section><h2>Контроль перед коммерческим решением</h2><ul>
<li>Сверить точные характеристики товара и применимые ГОСТ/ТУ по ТЗ.</li>
</ul><p>Этот список — общий контроль участника закупки.</p></section>
<section><h2>Источники</h2><ul>
<li>Извещение о закупке — раздел «Объект закупки», позиция 1</li>
</ul></section>
</main></body></html>"""


def _model() -> dict:
    return {
        "ai_runtime_provenance": {"producer": "production_llm_r10_1"},
        "procurement_number": DEFAULT_REGISTRY_NUMBER,
        "sentinel": {"must_remain": "unchanged"},
    }


def test_v3_closes_po_presentation_defects(monkeypatch) -> None:
    model = _model()
    snapshot = deepcopy(model)
    monkeypatch.setattr(
        refine_human_report_v3._v2,
        "rework_canonical_report",
        lambda _model, expected_registry_number: _v2_html(),
    )
    monkeypatch.setattr(
        refine_human_report_v3,
        "validate_customer_report",
        lambda _html, _registry: None,
    )

    rendered = refine_human_report_v3.refine_report_v3(
        model, expected_registry_number=DEFAULT_REGISTRY_NUMBER
    )

    assert model == snapshot
    assert "Предварительный отчёт для подготовки решения об участии" in rendered
    assert "Отчёт для принятия решения об участии" not in rendered
    assert "существенные условия, не извлечённые автоматически" in rendered
    assert "Техническая документация и проект контракта включены в комплект анализа" not in rendered

    assert "7 рабочих дней со дня подписания Заказчиком документа о приемке" not in rendered
    assert "автоматическое извлечение содержит внутренне неоднозначную" in rendered
    assert "срок и процедуру приёмки нужно проверить по проекту контракта" in rendered
    assert "Сверить формулировку срока и процедуры приёмки" in rendered

    assert "Проверить требования к составу заявки и участнику по Приложению 3" in rendered

    assert "Комплект документов, использованный для отчёта (6)" in rendered
    assert "Приложение 1 Описание объекта закупки" in rendered
    assert "Приложение 2 Обоснование НМЦК" in rendered
    assert "Приложение 3 Требования к составу заявки" in rendered
    assert "Приложение 4 Проект контракта" in rendered
    assert "Приложение 5 Реквизиты для обеспечения исполнения контракта" in rendered
    assert "Подтверждённые ссылки на конкретные факты" in rendered
    assert "раздел «Объект закупки», позиция 1" in rendered

    for internal in (
        "Product Owner",
        "REPORT_REWORK_REQUIRED",
        "NOT_AUTHORIZED",
        "NOT_ALLOWED",
        "BLOCKED_EXTERNAL_SOURCE",
        "P8.05",
    ):
        assert internal not in rendered


def test_v3_fails_closed_without_document_source_set(monkeypatch) -> None:
    html = _v2_html().replace(
        "<details><summary>Документы комплекта (6)</summary><ul>",
        "<details><summary>Комплект документов</summary><ul>",
        1,
    )
    monkeypatch.setattr(
        refine_human_report_v3._v2,
        "rework_canonical_report",
        lambda _model, expected_registry_number: html,
    )
    monkeypatch.setattr(
        refine_human_report_v3,
        "validate_customer_report",
        lambda _html, _registry: None,
    )

    with pytest.raises(
        AcceptanceBlocked, match="customer_report_document_sources_missing"
    ):
        refine_human_report_v3.refine_report_v3(
            _model(), expected_registry_number=DEFAULT_REGISTRY_NUMBER
        )
