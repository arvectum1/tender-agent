from __future__ import annotations

from copy import deepcopy

import pytest

from scripts.arv001 import rework_human_report
from scripts.arv001.complete_corpus_contract import (
    DEFAULT_REGISTRY_NUMBER,
    AcceptanceBlocked,
)

_RAW_XML = (
    "epNotificationEF2020_0388100001826000047_1_"
    "019F2033D80971F689A54DD1D878AF8C.xml"
)


def _accepted_report_html(extra: str = "") -> str:
    return f"""<!doctype html><html lang="ru"><body><main>
<section><h1>Анализ закупки № {DEFAULT_REGISTRY_NUMBER}</h1>
<p>Дизельное топливо; количество 140; НМЦК 25 200 000 ₽; ОКПД2 19.20.21.300.</p>
<p>Описание объекта закупки и технические требования подтверждены.</p>
<p>Проект контракта содержит условия оплаты, приемки, обеспечения и ответственности.</p>
<p>{extra}</p>
</section>
<section class="decision"><h2>Решение: Статус срока подачи не определён</h2>
<p><strong>Следующее действие:</strong> Сверить позиции с ТЗ.</p></section>
<section><h2>Состав и объём закупки</h2><p>Подробные требования приведены ниже в разделе «Технические требования».</p></section>
<section><h2>Технические требования</h2><table><tbody>
<tr><td>Сертификаты и паспорт качества</td><td>Нужны сертификаты.</td><td>{_RAW_XML}</td></tr>
</tbody></table></section>
<section><h2>Требования к заявке и участнику</h2><table><tbody>
<tr><td>Сертификаты и паспорт качества</td><td>Нужны сертификаты.</td><td>Техническое задание</td></tr>
</tbody></table></section>
<section><h2>Условия контракта</h2><h3>Оплата</h3>
<ul><li>Проект контракта содержит условия оплаты.</li></ul></section>
<section><h2>Коммерческие предложения</h2>
<p>Коммерческие предложения не загружены; экономика участия не рассчитана.</p></section>
<section><h2>Вопросы для уточнения</h2>
<p>Дополнительные вопросы по результатам анализа не сформированы.</p></section>
</main></body></html>"""


def _r10_model(*, with_analysis_time: bool = True) -> dict:
    model = {
        "ai_runtime_provenance": {
            "producer": "production_llm_r10_1",
        },
        "procurement_number": DEFAULT_REGISTRY_NUMBER,
        "application_deadline": "2026-07-10T18:30:00+12:00",
        "application_deadline_display": "10.07.2026 18:30 (UTC+12)",
        "customer_decision": {
            "recommendation": "Статус срока подачи не определён",
            "reasons": ["Основные реквизиты закупки подтверждены."],
            "confirmed": ["позиция и количество"],
            "next_action": "Сверить позиции с ТЗ.",
        },
        "line_items": [
            {
                "sequence": 1,
                "original_name": "Топливо дизельное",
                "quantity_display": "140",
                "unit_original": "т",
                "characteristics": [],
                "source_row": 1,
            }
        ],
        "requirements": [
            {
                "title": "Сертификаты и паспорт качества",
                "detail": "Нужны сертификаты.",
                "type": "техническое требование",
                "source": "Техническое задание",
            }
        ],
        "compatibility_sections": {
            "contract_highlights": ["Проект контракта содержит условия оплаты."],
        },
        "metadata": {
            "document_set_summary": {
                "status": "complete",
                "logical_document_count": 6,
                "physical_file_count": 10,
                "logical_documents": [],
            }
        },
        "sentinel": {"must_remain": "unchanged"},
    }
    if with_analysis_time:
        model["analysis_as_of_iso"] = "2026-08-27T06:50:02+03:00"
    return model


def test_report_rework_is_customer_facing_and_keeps_governance_out_of_html(
    monkeypatch,
) -> None:
    model = _r10_model()
    snapshot = deepcopy(model)
    monkeypatch.setattr(
        rework_human_report,
        "_render_customer_report_html",
        lambda _model: _accepted_report_html(
            "&lt;script&gt;alert(1)&lt;/script&gt;"
        ),
    )

    rendered = rework_human_report.rework_canonical_report(
        model,
        expected_registry_number=DEFAULT_REGISTRY_NUMBER,
    )

    assert model == snapshot
    assert "Предварительная рекомендация: НЕ УЧАСТВОВАТЬ" in rendered
    assert "К моменту формирования анализа срок уже истёк" in rendered
    assert "Ограничения текущего автоматического извлечения" in rendered
    assert "Детальные характеристики товара" in rendered
    assert "конкретный срок и порядок оплаты" in rendered
    assert "Размер и условия обеспечения исполнения контракта" in rendered
    assert "Контроль перед коммерческим решением" in rendered
    assert "Отдельные требования к составу заявки и участнику" in rendered
    assert "Подробные требования приведены ниже" not in rendered
    assert _RAW_XML not in rendered
    assert "Документы закупки" in rendered

    for internal in (
        "Product Owner",
        "REPORT_REWORK_REQUIRED",
        "NOT_AUTHORIZED",
        "NOT_ALLOWED",
        "BLOCKED_EXTERNAL_SOURCE",
        "P8.05",
        "Quality evidence",
    ):
        assert internal not in rendered

    assert '<h2>Решение:' not in rendered
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered
    assert "<script>alert(1)</script>" not in rendered


def test_report_rework_uses_hold_when_deadline_relation_is_not_provable(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        rework_human_report,
        "_render_customer_report_html",
        lambda _model: _accepted_report_html(),
    )

    rendered = rework_human_report.rework_canonical_report(
        _r10_model(with_analysis_time=False),
        expected_registry_number=DEFAULT_REGISTRY_NUMBER,
    )

    assert (
        "Предварительная рекомендация: HOLD — сначала вручную подтвердить "
        "актуальность срока подачи"
    ) in rendered
    assert "Текущий статус срока не удалось подтвердить" in rendered


def test_report_rework_fails_closed_on_independent_review_readiness(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        rework_human_report,
        "_render_customer_report_html",
        lambda _model: _accepted_report_html("Ready for independent review"),
    )

    with pytest.raises(
        AcceptanceBlocked,
        match="arv001_independent_review_readiness_forbidden",
    ):
        rework_human_report.rework_canonical_report(
            _r10_model(),
            expected_registry_number=DEFAULT_REGISTRY_NUMBER,
        )


def test_report_rework_rejects_non_r10_canonical_input() -> None:
    with pytest.raises(AcceptanceBlocked, match="canonical_report_not_r10_1"):
        rework_human_report.rework_canonical_report(
            {"ai_runtime_provenance": {"producer": "frozen_r9"}},
            expected_registry_number=DEFAULT_REGISTRY_NUMBER,
        )
