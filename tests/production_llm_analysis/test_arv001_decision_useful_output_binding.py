from __future__ import annotations

from types import SimpleNamespace

from src.modules.tender_operator_agent_demo import decision_useful_output_patch as output_patch
from src.modules.tender_operator_agent_demo import report_model, report_model_legacy, upload_service
from src.modules.tender_operator_agent_demo.decision_useful_extraction_v2 import (
    extract_decision_useful_analysis,
)


def _doc(role: str, name: str, text: str) -> SimpleNamespace:
    return SimpleNamespace(role=role, display_name=name, text=text)


def _documents() -> list[SimpleNamespace]:
    return [
        _doc(
            "technical_spec",
            "Описание объекта закупки.docx",
            "Топливо дизельное зимнее экологического класса К5 по ГОСТ 32511-2013. "
            "Предельная температура фильтруемости — не выше минус 32 °C. "
            "Цетановое число — не менее 51.",
        ),
        _doc(
            "contract_draft",
            "Проект контракта.docx",
            "Оплата поставленного товара осуществляется в течение 7 рабочих дней с даты подписания документа о приемке. Аванс не предусмотрен.\n"
            "Размер обеспечения исполнения Контракта составляет 5 % от цены Контракта. Обеспечение может быть предоставлено независимой гарантией или внесением денежных средств.\n"
            "Приемка осуществляется в течение 5 рабочих дней с даты поступления документа о приемке.\n"
            "Пеня начисляется за каждый день просрочки в размере 1/300 ключевой ставки Центрального банка Российской Федерации от не уплаченной в срок суммы.\n"
            "Штраф составляет 1 процент цены Контракта.\n"
            "Общая сумма начисленных штрафов не может превышать цену Контракта.\n",
        ),
        _doc(
            "application_requirements",
            "Требования к составу заявки.docx",
            "Заявка должна содержать декларацию о соответствии участника единым требованиям. "
            "Участник предоставляет в составе заявки документы, подтверждающие характеристики предлагаемого товара.",
        ),
    ]


def test_liability_cap_is_explicitly_extracted() -> None:
    analysis = extract_decision_useful_analysis(_documents())
    contract = analysis["contract"]
    assert contract["liability_cap_status"] == "found"
    assert len(contract["liability_cap"]) == 1
    assert "не может превышать цену Контракта" in contract["liability_cap"][0]["text"]


def test_security_can_be_recovered_from_notice_when_size_lives_there() -> None:
    documents = [
        _doc(
            "notice",
            "Извещение.xml",
            "Размер обеспечения исполнения контракта составляет 5 % от цены контракта. "
            "Обеспечение может быть предоставлено независимой гарантией или внесением денежных средств.",
        ),
        _doc(
            "contract_performance_security",
            "Реквизиты для обеспечения исполнения контракта.docx",
            "Получатель: Заказчик. Расчетный счет указан в реквизитах.",
        ),
    ]
    analysis = extract_decision_useful_analysis(documents)
    security = "\n".join(row["text"] for row in analysis["contract"]["security"])
    assert "5 %" in security
    assert "независимой гарантией" in security
    assert any(
        row["source"] == "Извещение о закупке"
        for row in analysis["contract"]["security"]
    )


def test_final_output_binding_uses_analysis_mode_argument_not_metadata(monkeypatch) -> None:
    outputs = {
        "requirements": {
            "requirements": [],
            "preliminary_analysis": {
                "contract_highlights": [
                    "Проект контракта содержит условия оплаты.",
                    "Проект контракта содержит условия ответственности сторон и штрафные санкции за нарушение обязательств.",
                ]
            },
            "analysis_context": {},
        }
    }
    monkeypatch.setattr(
        output_patch,
        "_BASE_BUILD_OUTPUT_PAYLOADS",
        lambda *_args, **_kwargs: outputs,
    )

    result = output_patch._build_output_payloads(
        metadata={},
        documents=_documents(),
        analysis_mode="production_llm_r10_1",
    )

    preliminary = result["requirements"]["preliminary_analysis"]
    highlights = "\n".join(preliminary["contract_highlights"])
    assert "Проект контракта содержит условия оплаты." not in highlights
    assert "7 рабочих дней" in highlights
    assert "5 %" in highlights
    assert "независимой гарантией" in highlights
    assert "1/300" in highlights
    assert "не может превышать цену Контракта" in highlights

    rows = result["requirements"]["requirements"]
    joined = "\n".join(f"{row.get('title')} {row.get('detail')}" for row in rows)
    assert "ГОСТ 32511-2013" in joined
    assert "экологического класса К5" in joined
    assert "декларацию" in joined

    context = result["requirements"]["analysis_context"]
    assert context["decision_useful_liability_cap_status"] == "found"
    assert context["decision_useful_liability_cap_count"] == 1


def _renderable_outputs() -> dict:
    return {
        "requirements": {
            "requirements": [],
            "preliminary_analysis": {
                "contract_highlights": [
                    "Проект контракта содержит условия оплаты.",
                    "Проект контракта содержит условия ответственности сторон и штрафные санкции за нарушение обязательств.",
                ],
                "overview": [],
                "next_actions": ["Сопоставить коммерческую цену с условиями контракта."],
                "spec_table": {"columns": [], "rows": []},
                "item_coverage": {},
            },
            "analysis_context": {
                "procurement_category": "goods",
                "procurement_scope": {},
                "document_coverage": "complete",
                "contract_draft_status": "present",
                "missing_documents": [],
                "okpd2_codes": [],
            },
        },
        "final_recommendation": {"recommendation": "needs_review", "rationale": []},
        "contract_risks": {"risks": []},
        "economics": {"metrics": [], "warnings": []},
        "supplier_questions": {"questions": []},
        "quotes_comparison": {"highlights": []},
    }


def _renderable_metadata() -> dict:
    logical_documents = [
        {"kind": "notice", "name": "Извещение о закупке", "type": "извещение"},
        {
            "kind": "technical_specification",
            "name": "Приложение 1 Описание объекта закупки",
            "type": "технический документ",
        },
        {
            "kind": "application_requirements",
            "name": "Приложение 3 Требования к составу заявки",
            "type": "требования к заявке",
        },
        {
            "kind": "contract_draft",
            "name": "Приложение 4 Проект контракта",
            "type": "проект контракта",
        },
    ]
    return {
        "run_id": "decision-useful-render-test",
        "procurement_id": "0388100001826000047",
        "procurement_title": "Поставка дизельного топлива",
        "customer_name": "Тестовый заказчик",
        "publication_date": "2026-07-02T12:21:00+12:00",
        "deadline": "2026-07-10T18:30:00+12:00",
        "analysis_completed_at": "2026-07-03T12:00:00+12:00",
        "analysis_mode": "production_llm_r10_1",
        "ai_runtime_provenance": {"producer": "production_llm_r10_1"},
        "procurement": {"initial_price": 25200000},
        "files": [
            {"display_name": "Извещение.xml", "role_hint": "notice"},
            {
                "display_name": "Приложение 1 Описание объекта закупки.docx",
                "role_hint": "technical_spec",
            },
            {
                "display_name": "Приложение 3 Требования к составу заявки.docx",
                "role_hint": "application_requirements",
            },
            {
                "display_name": "Приложение 4 Проект контракта.docx",
                "role_hint": "contract_draft",
            },
        ],
        "document_set_summary": {
            "status": "complete",
            "physical_file_count": 4,
            "logical_document_count": 4,
            "missing_required_document_kinds": [],
            "logical_documents": logical_documents,
        },
    }


def test_material_details_survive_canonical_model_and_customer_html(monkeypatch) -> None:
    outputs = _renderable_outputs()
    analysis = extract_decision_useful_analysis(_documents())
    output_patch._inject_exact_requirements(outputs, analysis)

    monkeypatch.setattr(
        report_model_legacy,
        "get_settings",
        lambda: SimpleNamespace(source_graph_mode="legacy"),
    )
    model = report_model.build_procurement_report_model(
        _renderable_metadata(), outputs, repository_sha="test-sha"
    )
    rendered = upload_service._render_customer_report_html(model)

    required_material_details = (
        "ГОСТ 32511-2013",
        "экологического класса К5",
        "минус 32",
        "Цетановое число",
        "7 рабочих дней",
        "Аванс не предусмотрен",
        "5 %",
        "независимой гарантией",
        "5 рабочих дней",
        "1/300 ключевой ставки",
        "не уплаченной в срок суммы",
        "1 процент цены Контракта",
        "не может превышать цену Контракта",
        "декларацию о соответствии участника",
    )
    for value in required_material_details:
        assert value in rendered

    assert "Проект контракта содержит условия оплаты." not in rendered
    assert (
        "Проект контракта содержит условия ответственности сторон и штрафные санкции"
        not in rendered
    )
