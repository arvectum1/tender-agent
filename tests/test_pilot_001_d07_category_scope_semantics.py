from __future__ import annotations

import pytest

from src.modules.tender_operator_agent_demo.goods_source_facts import extract_goods_source_facts
from src.modules.tender_operator_agent_demo.upload_service import (
    AnalyzedDocument,
    _build_document_grounded_requirements,
    _build_preliminary_procurement_analysis,
    _classify_procurement_scope,
)


def _document(text: str, *, role: str = "contract_draft", file_id: str = "FILE-01") -> AnalyzedDocument:
    return AnalyzedDocument(
        display_name={"contract_draft": "Проект контракта.docx", "technical_spec": "Техническое задание.docx"}.get(role, "Извещение.xml"),
        extension=".docx",
        role=role,
        text=text,
        extracted_text_available=True,
        warnings=[],
        source="historical",
        file_id=file_id,
        raw_content=None,
    )


def _scope(text: str, *, title: str = "Закупка", role: str = "contract_draft") -> dict:
    return _classify_procurement_scope({"tender_title": title, "procurement": {}}, [_document(text, role=role)], title)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Поставщик обязуется поставить товар Заказчику. Срок поставки товара — 10 дней.", "goods"),
        ("Исполнитель обязуется оказать услуги Заказчику в соответствии с контрактом.", "services"),
        ("Арендодатель предоставляет имущество во временное пользование. Арендная плата вносится ежемесячно.", "rental"),
        ("Подрядчик обязуется выполнить работы. Результат работ передается по акту выполненных работ.", "works"),
    ],
)
def test_d07_classifies_unambiguous_procurement_subjects(text: str, expected: str):
    assert _scope(text)["procurement_primary_scope"] == expected


def test_d07_rental_dominates_product_like_rows_and_standards():
    text = """Арендодатель предоставляет медицинское оборудование во временное пользование.
Арендная плата вносится ежемесячно; срок аренды — 12 месяцев.
1\tСветильник хирургический\t12\tшт.
Оборудование соответствует ГОСТ 12345-2020.
"""
    scope = _scope(text, title="Аренда медицинского оборудования", role="technical_spec")

    assert scope["procurement_primary_scope"] == "rental"
    assert scope["goods_extraction_applicable"] is False
    assert scope["contains_goods"] is False


def test_d07_goods_subject_is_not_overridden_by_incidental_services_wording():
    scope = _scope(
        "Поставщик обязуется поставить товар. Услуги связи при исполнении договора оплачиваются поставщиком.",
        title="Поставка оборудования",
    )
    assert scope["procurement_primary_scope"] == "goods"


def test_d07_independent_goods_and_services_subjects_are_mixed():
    documents = [
        _document("Поставщик обязуется поставить товар Заказчику.", file_id="FILE-01"),
        _document("Исполнитель обязуется оказать услуги по монтажу и сопровождению.", file_id="FILE-02"),
    ]
    scope = _classify_procurement_scope({"tender_title": "Комплексная закупка", "procurement": {}}, documents, "Комплексная закупка")
    assert scope["procurement_primary_scope"] == "mixed"
    assert scope["goods_extraction_applicable"] is False


def test_d07_weak_conflicting_words_fail_closed_as_unresolved():
    scope = _scope("Товар и услуги указаны в приложении.", title="Закупка", role="supporting")
    assert scope["procurement_primary_scope"] == "unresolved"
    assert scope["goods_extraction_applicable"] is False


def test_d07_decision_carries_document_provenance_and_basis():
    scope = _scope("Арендодатель предоставляет имущество во временное пользование.")
    evidence = next(item for item in scope["classification_evidence"] if item["category"] == "rental")

    assert evidence["source_document"] == "Проект контракта.docx"
    assert evidence["file_id"] == "FILE-01"
    assert evidence["locator"] == "line:1"
    assert "временное пользование" in evidence["excerpt"]
    assert evidence["semantic_role"] == "CONTRACT_DRAFT"
    assert evidence["weight"] > 0
    assert scope["scope_decision_basis"]


def test_d07_rental_suppresses_goods_requirements_but_keeps_source_facts_for_audit():
    document = _document(
        """Арендодатель предоставляет имущество во временное пользование.
Арендная плата вносится ежемесячно.
Поставка товара упомянута только в типовой форме приемки.
1\tСветильник хирургический\t12\tшт.
""",
        role="technical_spec",
    )
    scope = _classify_procurement_scope({"tender_title": "Аренда оборудования", "procurement": {}}, [document], "Аренда оборудования")
    preliminary = _build_preliminary_procurement_analysis(
        metadata={"tender_title": "Аренда оборудования", "procurement": {"delivery_term": None}},
        documents=[document],
        technical_spec_text=document.text,
        contract_draft_text="",
        notice_text=document.text,
    )

    assert scope["procurement_primary_scope"] == "rental"
    assert _build_document_grounded_requirements([document], "rental") == []
    assert extract_goods_source_facts([document])
    assert preliminary["procurement_kind"] == "rental"
    assert preliminary["supply_section_note"].startswith("Товарный анализ не запускается")
