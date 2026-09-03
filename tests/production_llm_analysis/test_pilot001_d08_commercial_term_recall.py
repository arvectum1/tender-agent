from __future__ import annotations

from src.modules.procurement_analysis.frozen_types import AnalyzedDocument
from src.modules.tender_operator_agent_demo import upload_service
from src.modules.tender_operator_agent_demo.commercial_term_recall_patch import (
    extract_commercial_term_recall,
)


def _document(
    *,
    name: str,
    role: str,
    text: str,
    page: int,
    file_id: str,
) -> AnalyzedDocument:
    return AnalyzedDocument(
        display_name=name,
        extension=".txt",
        role=role,
        text=text,
        extracted_text_available=True,
        warnings=[],
        source="persisted_procurement_intake",
        file_id=file_id,
        evidence_chunks=[
            {
                "document_id": file_id,
                "document_name": name,
                "chunk_id": f"{file_id}:chunk:0",
                "locator": {"page": page, "chunk_index": 0},
                "text": text,
            }
        ],
    )


def _source_documents() -> list[AnalyzedDocument]:
    return [
        _document(
            name="Описание объекта закупки.txt",
            role="technical_spec",
            text=(
                "Срок поставки товара составляет 10 рабочих дней с даты "
                "заключения контракта. Поставка осуществляется одной партией."
            ),
            page=4,
            file_id="1" * 64,
        ),
        _document(
            name="Проект контракта.txt",
            role="contract_draft",
            text=(
                "Оплата поставленного товара осуществляется в течение 7 рабочих "
                "дней после подписания документа о приемке.\n"
                "Не позднее 5 рабочих дней после поступления документа о приемке "
                "Заказчик подписывает документ либо направляет мотивированный отказ."
            ),
            page=8,
            file_id="2" * 64,
        ),
    ]


def test_d08_recovers_three_source_visible_commercial_terms_with_evidence() -> None:
    facts = extract_commercial_term_recall(_source_documents())
    by_kind = {row["kind"]: row for row in facts}

    assert set(by_kind) == {
        "delivery_period",
        "payment_terms",
        "acceptance_signing_deadline",
    }
    assert "10 рабочих дней" in by_kind["delivery_period"]["text"]
    assert "7 рабочих дней" in by_kind["payment_terms"]["text"]
    assert "5 рабочих дней" in by_kind["acceptance_signing_deadline"]["text"]

    delivery_ref = by_kind["delivery_period"]["evidence_reference"]
    payment_ref = by_kind["payment_terms"]["evidence_reference"]
    assert delivery_ref["document_name"] == "Описание объекта закупки.txt"
    assert delivery_ref["locator"]["page"] == 4
    assert delivery_ref["chunk_id"].endswith(":chunk:0")
    assert payment_ref["document_name"] == "Проект контракта.txt"
    assert payment_ref["locator"]["page"] == 8


def test_d08_rejects_generic_or_non_payment_mentions_without_explicit_timing() -> None:
    documents = [
        _document(
            name="Проект контракта.txt",
            role="contract_draft",
            text=(
                "Расчет цены контракта выполнен методом сопоставимых рыночных цен.\n"
                "Поставка товара осуществляется силами Поставщика.\n"
                "Приемка товара осуществляется комиссией Заказчика."
            ),
            page=3,
            file_id="3" * 64,
        )
    ]

    assert extract_commercial_term_recall(documents) == []


def test_d08_report_side_highlights_keep_exact_fact_and_public_locator() -> None:
    documents = _source_documents()
    result = upload_service._build_preliminary_procurement_analysis(
        metadata={
            "analysis_mode": "production_llm_r10_1",
            "tender_title": "Поставка тестового товара",
            "tender_category": "Товары",
            "procurement": {},
        },
        documents=documents,
        technical_spec_text=documents[0].text or "",
        contract_draft_text=documents[1].text or "",
        notice_text="",
    )

    highlights = result["contract_highlights"]
    assert any(
        "Срок поставки:" in value
        and "10 рабочих дней" in value
        and "Описание объекта закупки.txt" in value
        and "страница: 4" in value
        for value in highlights
    )
    assert any(
        "Условия оплаты:" in value
        and "7 рабочих дней" in value
        and "Проект контракта.txt" in value
        and "страница: 8" in value
        for value in highlights
    )
    assert any(
        "Срок приёмки / подписания:" in value
        and "5 рабочих дней" in value
        and "страница: 8" in value
        for value in highlights
    )

    facts = result["commercial_term_recall"]
    assert all(row.get("evidence_reference") for row in facts)
    assert all("file_id" not in str(row.get("source_display", "")) for row in facts)
