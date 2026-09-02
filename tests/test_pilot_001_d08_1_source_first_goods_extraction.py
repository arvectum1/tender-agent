from __future__ import annotations

from types import SimpleNamespace

from src.modules.tender_operator_agent_demo.goods_source_facts import (
    build_goods_requirements_from_source_facts,
    detect_procurement_richness,
    extract_goods_source_facts,
    semantic_procurement_role,
)
from src.modules.tender_operator_agent_demo.grounded_fallback_evidence_binding import (
    _bind_fallback_evidence,
)
from src.modules.tender_operator_agent_demo.upload_service_legacy import (
    _build_goods_requirement_rows,
    _collect_unmerged_source_items,
)


def _doc(text: str, *, name: str = "attachment.pdf", role: str = "supporting", file_id: str = "FILE-01"):
    return SimpleNamespace(file_id=file_id, display_name=name, extension=name[name.rfind(".") :], role=role, text=text, evidence_chunks=[])


def test_neutral_filename_rich_document_is_semantically_technical_and_eligible():
    document = _doc("Описание объекта закупки\nНаименование товара: Аккумуляторная батарея\nКоличество: 20 шт.", name="Приложение № 1.docx")
    facts = extract_goods_source_facts([document])
    assert semantic_procurement_role(document) == "TECHNICAL_SPEC"
    assert detect_procurement_richness(document)
    assert {fact.fact_type for fact in facts} >= {"PRODUCT_ITEM", "QUANTITY"}


def test_neutral_filename_and_supporting_role_do_not_gate_extraction():
    document = _doc("Степень защиты: IP54\nНоминальное напряжение: 220 В.")
    facts = extract_goods_source_facts([document])
    assert {fact.value for fact in facts if fact.fact_type == "PRODUCT_CHARACTERISTIC"} == {"Степень защиты IP54", "Номинальное напряжение 220 В"}


def test_concrete_source_facts_carry_exact_provenance():
    document = _doc(
        "Наименование товара: Аккумуляторная батарея\nНапряжение: 12 В\nЁмкость: 100 Ач\nКоличество: 20 шт.\nГОСТ 12345-2020\nСрок поставки: 15 календарных дней.",
        name="neutral.txt",
    )
    facts = extract_goods_source_facts([document])
    assert {fact.fact_type for fact in facts} >= {"PRODUCT_ITEM", "PRODUCT_CHARACTERISTIC", "QUANTITY", "STANDARD", "DELIVERY_DEADLINE"}
    assert all(fact.source_document and fact.file_id and fact.locator and fact.excerpt for fact in facts)


def test_keyword_only_text_does_not_invent_material_facts():
    facts = extract_goods_source_facts([_doc("Нормативные документы и требования безопасности приведены в приложениях.")])
    assert facts == []


def test_contract_delivery_place_and_warranty_are_source_facts():
    facts = extract_goods_source_facts([_doc("Проект контракта\nСрок поставки: 10 рабочих дней.\nМесто поставки: г. Киров, ул. Ленина, 1.\nГарантийный срок: 24 месяца.", name="contract.docx", role="contract_draft")])
    assert {fact.fact_type for fact in facts} >= {"DELIVERY_DEADLINE", "DELIVERY_PLACE", "WARRANTY"}


def test_generic_templates_are_not_goods_requirements():
    assert _build_goods_requirement_rows([_doc("Короткий нейтральный текст.")]) == []


def test_source_first_requirement_binds_exact_extraction_time_evidence():
    fact = next(fact for fact in extract_goods_source_facts([_doc("ГОСТ 12345-2020")]) if fact.fact_type == "STANDARD")
    rows = build_goods_requirements_from_source_facts([fact])
    outputs = {"requirements": {"requirements": rows}, "trace": {"grounding_policy": "source_bound_v1", "fallback_category": "GOODS"}}
    result = _bind_fallback_evidence(outputs, documents=[])["requirements"]["requirements"][0]
    assert result["evidence_state"] == "bound"
    assert result["evidence_ids"] == [fact.fact_id]


def test_all_text_source_item_fallback_deduplicates_specialized_paths():
    document = _doc("1\tАккумуляторная батарея\t20\tшт.", name="neutral.docx")
    items = _collect_unmerged_source_items([document])
    facts = extract_goods_source_facts([document])
    assert len(items) == 1
    assert items[0].name == "Аккумуляторная батарея"
    assert any(fact.fact_type == "QUANTITY" and fact.value == "20" and fact.unit == "шт." for fact in facts)


def test_d08_forensic_shape_has_facts_without_templates():
    documents = [
        _doc("<purchaseNotice>Извещение</purchaseNotice>", name="notice.xml", role="notice", file_id="N"),
        _doc("Описание объекта закупки\nНаименование товара: Кабель\nКоличество: 10 шт.\nНапряжение: 220 В", name="Приложение 1.docx", file_id="A"),
        _doc("ГОСТ 12345-2020\nГарантийный срок: 24 месяца.", name="Приложение 2.pdf", file_id="B"),
        _doc("Обоснование НМЦК\n1\tКабель\t10\tшт.", name="НМЦК.xlsx", file_id="C"),
        _doc("Проект контракта\nСрок поставки: 10 рабочих дней.", name="contract.docx", role="contract_draft", file_id="D"),
    ]
    facts = extract_goods_source_facts(documents)
    requirements = _build_goods_requirement_rows(documents)
    assert sum(detect_procurement_richness(document) for document in documents) >= 2
    assert facts and requirements
    assert not {row["title"] for row in requirements} & {"Соответствие ГОСТ / ТУ", "Сертификаты и паспорт качества", "Маркировка и безопасность", "Доставка до заказчика"}
