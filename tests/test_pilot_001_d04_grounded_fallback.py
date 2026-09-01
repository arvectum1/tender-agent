from __future__ import annotations

import json

from src.modules.tender_operator_agent_demo.upload_service import (
    AnalyzedDocument,
    _build_goods_economics_payload,
    _build_goods_requirement_rows,
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


def test_d04_goods_fallback_has_source_bound_category_and_no_generic_claims():
    result = _preliminary(
        "Поставка автоматических выключателей",
        "Поставка автоматических выключателей. Количество 10 штук.",
    )
    rendered = json.dumps(result, ensure_ascii=False).lower()

    assert result["grounded_fallback_category"] == "GOODS"
    assert result["grounding_policy"] == "source_bound_v1"
    assert "15 рабочих дней" not in rendered
    assert "доставка и разгрузка должны" not in rendered
    assert "складской остаток и срок отгрузки" not in rendered
    assert "общий объём кабеля/провода" not in rendered
    assert "INSUFFICIENT_EVIDENCE" in json.dumps(result, ensure_ascii=False)


def test_d04_goods_economics_replaces_unsupported_material_conditions():
    documents = [_document("Поставка автоматических выключателей. Количество 10 штук.")]
    payload = _build_goods_economics_payload(
        {"tender_title": "Поставка автоматических выключателей"},
        documents,
        "fallback_deterministic_adapter",
        None,
    )
    rendered = json.dumps(payload, ensure_ascii=False).lower()

    assert "15 рабочих дней" not in rendered
    assert "проверить, включены ли доставка, разгрузка" not in rendered
    assert payload["grounding_status"] == "source_bound"
    assert "INSUFFICIENT_EVIDENCE" in json.dumps(payload, ensure_ascii=False)


def test_d04_goods_requirement_rows_do_not_fabricate_technical_spec_source():
    rows = _build_goods_requirement_rows([])
    assert rows == []


def test_d04_services_fallback_does_not_inherit_goods_or_resource_assumptions():
    result = _preliminary(
        "Оказание услуг по уборке помещений",
        "Оказание услуг по уборке помещений административного здания.",
    )
    rendered = json.dumps(result, ensure_ascii=False).lower()

    assert result["grounded_fallback_category"] == "SERVICES"
    assert "доставка и разгрузка" not in rendered
    assert "наличие товара на складе" not in rendered
    assert "ремонтной базы" not in rendered
    assert "INSUFFICIENT_EVIDENCE" in json.dumps(result, ensure_ascii=False)


def test_d04_generic_works_fallback_does_not_inherit_software_template():
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


def test_d04_source_backed_delivery_requirement_is_not_suppressed():
    result = _preliminary(
        "Поставка светильников",
        "Поставка светильников. Срок поставки 20 календарных дней. "
        "Доставка выполняется до адреса заказчика.",
    )
    rendered = json.dumps(result, ensure_ascii=False).lower()

    assert result["grounded_fallback_category"] == "GOODS"
    assert "20 календарных дней" in rendered
    assert "срок поставки" in rendered
