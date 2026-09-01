from __future__ import annotations

import json

from src.modules.tender_operator_agent_demo.grounded_fallback_patch import (
    _ground_list,
    _sanitize_fallback_outputs,
    _source_corpus,
)
from src.modules.tender_operator_agent_demo.upload_service import (
    AnalyzedDocument,
    _build_preliminary_procurement_analysis,
)


def _document(text: str, *, name: str = "technical_spec.txt") -> AnalyzedDocument:
    return AnalyzedDocument(
        display_name=name,
        extension=".txt",
        role="technical_spec",
        text=text,
        extracted_text_available=True,
        warnings=[],
        source="upload",
        file_id="FILE-D04",
        raw_content=None,
    )


def _preliminary(title: str, text: str):
    documents = [_document(text)]
    return _build_preliminary_procurement_analysis(
        metadata={"tender_title": title, "procurement": {"delivery_term": None}},
        documents=documents,
        technical_spec_text=text,
        contract_draft_text="",
        notice_text=text,
    )


def test_d04_goods_preliminary_is_source_bound_and_has_no_generic_claims():
    result = _preliminary(
        "Поставка автоматических выключателей",
        "Поставка автоматических выключателей. Количество 10 штук.",
    )
    rendered = json.dumps(result, ensure_ascii=False).lower()

    assert result["grounded_fallback_category"] == "GOODS"
    assert result["grounding_policy"] == "source_bound_v1"
    assert "доставка и разгрузка должны" not in rendered
    assert "складской остаток и срок отгрузки" not in rendered
    assert "общий объём кабеля/провода" not in rendered
    assert "INSUFFICIENT_EVIDENCE" in json.dumps(result, ensure_ascii=False)


def test_d04_services_preliminary_does_not_inherit_resource_assumptions():
    result = _preliminary(
        "Оказание услуг по уборке помещений",
        "Оказание услуг по уборке помещений административного здания.",
    )
    rendered = json.dumps(result, ensure_ascii=False).lower()

    assert result["grounded_fallback_category"] == "SERVICES"
    assert "ремонтной базы" not in rendered
    assert "наличие специалистов" not in rendered
    assert "INSUFFICIENT_EVIDENCE" in json.dumps(result, ensure_ascii=False)


def test_d04_generic_works_preliminary_does_not_inherit_software_template():
    result = _preliminary(
        "Выполнение работ по ремонту кровли",
        "Выполнение работ по ремонту кровли административного здания.",
    )
    rendered = json.dumps(result, ensure_ascii=False).lower()

    assert result["grounded_fallback_category"] == "WORKS"
    assert "модифицированный модуль" not in rendered
    assert "интеграционного контура заказчика" not in rendered
    assert "передаче лицензии" not in rendered
    assert "INSUFFICIENT_EVIDENCE" in json.dumps(result, ensure_ascii=False)


def test_d04_source_backed_delivery_deadline_is_retained():
    source = "Срок поставки: 20 календарных дней с даты заключения контракта."
    corpus = _source_corpus([_document(source)])
    grounded = _ground_list(
        ["Срок поставки: 20 календарных дней."],
        corpus=corpus,
    )

    assert grounded == ["Срок поставки: 20 календарных дней."]


def test_d04_payment_period_does_not_ground_an_invented_delivery_deadline():
    source = "Оплата производится в течение 7 рабочих дней после приемки."
    corpus = _source_corpus([_document(source)])
    grounded = _ground_list(
        ["Товар должен быть поставлен в срок 15 рабочих дней по заявке."],
        corpus=corpus,
    )
    rendered = " ".join(grounded).lower()

    assert "15 рабочих дней" not in rendered
    assert grounded[0].startswith("INSUFFICIENT_EVIDENCE:")


def test_d04_output_sanitizer_removes_pilot_regression_templates():
    documents = [_document("Поставка автоматических выключателей. Количество 10 штук.")]
    corpus = _source_corpus(documents)
    outputs = {
        "tender_summary": {},
        "requirements": {
            "requirements": [
                {
                    "title": "Доставка до заказчика",
                    "detail": "Доставка и разгрузка должны быть включены.",
                    "source": "Техническое задание",
                    "type": "логистика",
                }
            ],
            "analysis_context": {},
        },
        "supplier_questions": {
            "questions": [
                "Подтвердите срок поставки 15 рабочих дней и наличие товара на складе."
            ],
            "ambiguities": [],
        },
        "rfq_draft": {
            "sections": [
                "Срок поставки, наличие на складе, доставка и разгрузка"
            ]
        },
        "economics": {
            "metrics": [],
            "drivers": [
                "Для решения нужны КП, включая доставку и документы качества."
            ],
            "manual_checks": [
                "Сверить наличие товара и срок поставки в течение 15 рабочих дней."
            ],
        },
        "contract_risks": {
            "risks": [
                {
                    "risk": "Риск по сроку поставки",
                    "severity": "warning",
                    "impact": "Товар может не уложиться в срок 15 рабочих дней.",
                    "mitigation": "Подтвердить склад, доставку, барабаны и разгрузку.",
                }
            ],
            "manual_checks": [
                "Проверить договорные ограничения и совместимость аналогов вручную."
            ],
        },
        "final_recommendation": {
            "rationale": [
                "Для участия нужно подтвердить ГОСТ, сертификаты и сроки поставки.",
                "Финальное решение возможно после проверки логистики и документов качества.",
            ],
            "key_requirements": [],
            "open_questions": [],
            "risks": [],
            "economics": [],
        },
        "trace": {},
    }

    sanitized = _sanitize_fallback_outputs(
        outputs,
        documents=documents,
        corpus=corpus,
        category="GOODS",
    )
    rendered = json.dumps(sanitized, ensure_ascii=False).lower()

    assert "15 рабочих дней" not in rendered
    assert "барабаны" not in rendered
    assert "доставка и разгрузка должны" not in rendered
    assert sanitized["requirements"]["requirements"] == []
    assert sanitized["final_recommendation"]["grounding_status"] == "source_bound"
    assert sanitized["trace"]["grounding_policy"] == "source_bound_v1"
    assert "INSUFFICIENT_EVIDENCE" in json.dumps(sanitized, ensure_ascii=False)
