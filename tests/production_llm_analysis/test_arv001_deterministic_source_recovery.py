from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi import HTTPException

from src.modules.customer_pilot.input_resolver import _reconstruct_persisted_document_text
from src.modules.procurement_analysis.frozen_types import AnalyzedDocument
from src.modules.tender_operator_agent_demo import upload_service
from src.tender_research.document_text_extractor import _extract_xml


REGISTRY = "0388100001826000047"

EIS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<epNotification xmlns="urn:arvectum:test:eis">
  <commonInfo>
    <purchaseNumber>0388100001826000047</purchaseNumber>
    <maxPrice>25200000</maxPrice>
  </commonInfo>
  <purchaseObjects>
    <purchaseObject>
      <purchaseObjectInfo>Дизельное топливо</purchaseObjectInfo>
      <OKPD2>
        <OKPDCode>19.20.21.300</OKPDCode>
        <OKPDName>Топливо дизельное</OKPDName>
      </OKPD2>
      <quantity><value>140</value></quantity>
      <OKEI><nationalCode>л</nationalCode></OKEI>
    </purchaseObject>
  </purchaseObjects>
</epNotification>
""".encode("utf-8")

CONTRACT_TEXT = """
Проект контракта.
Порядок оплаты. Заказчик производит оплату после приемки поставленного товара.
Не позднее 5 рабочих дней после поступления документа о приемке заказчик подписывает документ.
Обеспечение исполнения контракта составляет 5 % от НМЦК.
Ответственность сторон установлена проектом контракта; предусмотрены штрафы за нарушение обязательств.
""".strip()


@dataclass
class Chunk:
    text: str
    char_start: int
    char_end: int


def test_xml_extraction_preserves_structured_eis_fields() -> None:
    extracted = _extract_xml(EIS_XML)

    assert "purchaseObject" in extracted
    assert "maxPrice" in extracted
    assert "OKPDCode" in extracted
    assert "Дизельное топливо" in extracted


def test_persisted_chunk_reconstruction_removes_overlap_exactly() -> None:
    source = "<root><purchaseObject>Дизельное топливо</purchaseObject></root>"
    chunks = [
        Chunk(source[:38], 0, 38),
        Chunk(source[28:55], 28, 55),
        Chunk(source[45:], 45, len(source)),
    ]

    assert _reconstruct_persisted_document_text(chunks) == source


def test_persisted_chunk_reconstruction_fails_closed_on_conflicting_overlap() -> None:
    chunks = [
        Chunk("abcdefghij", 0, 10),
        Chunk("XXXXXklmnop", 5, 16),
    ]

    with pytest.raises(HTTPException, match="overlap is inconsistent"):
        _reconstruct_persisted_document_text(chunks)


def _documents() -> list[AnalyzedDocument]:
    xml_text = _extract_xml(EIS_XML)
    return [
        AnalyzedDocument(
            display_name="Извещение.xml",
            extension=".xml",
            role="notice",
            text=xml_text,
            extracted_text_available=True,
            warnings=[],
            source="persisted_procurement_intake",
            file_id="1" * 64,
        ),
        AnalyzedDocument(
            display_name="Описание объекта закупки.txt",
            extension=".txt",
            role="technical_spec",
            text="Техническое задание. Поставка дизельного топлива в соответствии с извещением.",
            extracted_text_available=True,
            warnings=[],
            source="persisted_procurement_intake",
            file_id="2" * 64,
        ),
        AnalyzedDocument(
            display_name="Проект контракта.txt",
            extension=".txt",
            role="contract_draft",
            text=CONTRACT_TEXT,
            extracted_text_available=True,
            warnings=[],
            source="persisted_procurement_intake",
            file_id="3" * 64,
        ),
    ]


def _metadata() -> dict:
    return {
        "run_id": "arv001-test-run",
        "procurement_id": REGISTRY,
        "tender_title": "Поставка дизельного топлива",
        "tender_category": "Товары",
        "customer_name": "Тестовый заказчик",
        "status": "completed",
        "mode": "production_llm_r10_1",
        "analysis_mode": "production_llm_r10_1",
        "warnings": [],
        "limitations": [],
        "files": [
            {"display_name": "Извещение.xml"},
            {"display_name": "Описание объекта закупки.txt"},
            {"display_name": "Проект контракта.txt"},
        ],
        "procurement": {
            "registry_number": REGISTRY,
        },
    }


def test_r10_1_deterministic_layer_recovers_arv001_five_facts() -> None:
    documents = _documents()
    notice_text = documents[0].text or ""
    technical_text = documents[1].text or ""
    contract_text = documents[2].text or ""

    metadata = upload_service._enrich_procurement_metadata_from_documents(
        _metadata(),
        documents=documents,
        combined_text="\n".join(doc.text or "" for doc in documents),
        notice_text=notice_text,
        technical_spec_text=technical_text,
        contract_draft_text=contract_text,
    )

    extracted = upload_service._collect_unmerged_source_items(documents)
    assert len(extracted) == 1
    assert "дизель" in extracted[0].name.lower()
    assert extracted[0].quantity == "140"
    assert extracted[0].okpd2 == "19.20.21.300"

    procurement = metadata["procurement"]
    assert float(procurement["initial_price"]) == 25_200_000
    assert any(item.get("code") == "19.20.21.300" for item in procurement["okpd2_codes"])

    outputs = upload_service._build_output_payloads(
        metadata=metadata,
        documents=documents,
        analysis_mode="production_llm_r10_1",
        requirements={"technical_requirements": [], "document_requirements": []},
        calibrated_risks=[],
        supplier_questions=[],
        tkp_comparison=None,
        economics=None,
        bid_decision=None,
        core_complete=False,
        quote_inputs_present=False,
    )

    requirements = outputs["requirements"]
    context = requirements["analysis_context"]
    canonical_items = requirements["preliminary_analysis"]["canonical_procurement_model"]["canonical_items"]

    assert len(canonical_items) == 1
    assert "дизель" in canonical_items[0]["display_name"].lower()
    assert canonical_items[0]["quantity"] == "140"
    assert canonical_items[0]["okpd2"] == "19.20.21.300"
    assert context["nmck"].replace(" ", "").replace(",00", "") == "25200000"
    assert any("оплат" in item.lower() for item in context["known_contract_terms"])
