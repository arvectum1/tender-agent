from __future__ import annotations

from types import SimpleNamespace

from src.modules.tender_operator_agent_demo import decision_useful_runtime_patch as patch
from src.modules.tender_operator_agent_demo.decision_useful_extraction import (
    extract_decision_useful_analysis,
    material_detail_count,
)


def _doc(role: str, name: str, text: str) -> SimpleNamespace:
    return SimpleNamespace(role=role, display_name=name, text=text)


def _documents() -> list[SimpleNamespace]:
    return [
        _doc(
            "technical_spec",
            "Приложение 1 Описание объекта закупки.docx",
            """
            Топливо дизельное зимнее экологического класса К5 должно соответствовать ГОСТ 32511-2013.
            Предельная температура фильтруемости топлива — не выше минус 32 °C.
            Цетановое число — не менее 51.
            """,
        ),
        _doc(
            "contract_draft",
            "Приложение 4 Проект контракта.docx",
            """
            Оплата поставленного Товара осуществляется Заказчиком в течение 7 рабочих дней с даты подписания документа о приемке. Аванс не предусмотрен.
            Размер обеспечения исполнения Контракта составляет 5 % от цены Контракта. Обеспечение может быть предоставлено независимой гарантией или внесением денежных средств.
            Заказчик осуществляет приемку в течение 5 рабочих дней с даты поступления документа о приемке.
            Пеня начисляется за каждый день просрочки в размере одной трехсотой действующей ключевой ставки Центрального банка Российской Федерации от не уплаченной в срок суммы.
            Штраф за ненадлежащее исполнение обязательства составляет 1 процент цены Контракта.
            Общая сумма начисленных штрафов не может превышать цену Контракта.
            Заказчик вправе принять решение об одностороннем отказе от исполнения Контракта в предусмотренных законом случаях.
            """,
        ),
        _doc(
            "application_requirements",
            "Приложение 3 Требования к составу заявки.docx",
            """
            Заявка должна содержать декларацию о соответствии участника единым требованиям.
            Участник предоставляет в составе заявки документы, подтверждающие характеристики предлагаемого товара.
            """,
        ),
    ]


def test_extracts_decision_useful_material_terms() -> None:
    analysis = extract_decision_useful_analysis(_documents())

    assert "ГОСТ 32511-2013" in analysis["technical"]["standards"]
    technical_text = " ".join(
        row["text"] for row in analysis["technical"]["specific_clauses"]
    )
    assert "экологического класса К5" in technical_text
    assert "минус 32" in technical_text
    assert "Цетановое число" in technical_text

    payment = " ".join(row["text"] for row in analysis["contract"]["payment"])
    assert "7 рабочих дней" in payment
    assert "Аванс не предусмотрен" in payment

    security = " ".join(row["text"] for row in analysis["contract"]["security"])
    assert "5 %" in security
    assert "независимой гарантией" in security

    acceptance = " ".join(row["text"] for row in analysis["contract"]["acceptance"])
    assert "5 рабочих дней" in acceptance

    liability = " ".join(row["text"] for row in analysis["contract"]["liability"])
    assert "ключевой ставки" in liability
    assert "1 процент цены Контракта" in liability

    termination = " ".join(row["text"] for row in analysis["contract"]["termination"])
    assert "одностороннем отказе" in termination

    application = " ".join(row["text"] for row in analysis["application_requirements"])
    assert "декларацию" in application
    assert "характеристики предлагаемого товара" in application
    assert material_detail_count(analysis) >= 9

    for group in (
        analysis["technical"]["specific_clauses"],
        analysis["contract"]["payment"],
        analysis["contract"]["liability"],
        analysis["application_requirements"],
    ):
        assert all(row["source"] for row in group)
        assert all(row["locator"]["char_end"] > row["locator"]["char_start"] for row in group)


def test_r10_1_preliminary_replaces_generic_contract_flags(monkeypatch) -> None:
    monkeypatch.setattr(
        patch,
        "_ORIGINAL_PRELIMINARY",
        lambda **_kwargs: {
            "contract_highlights": [
                "Проект контракта содержит условия оплаты.",
                "Цена контракта: твердая, без индексации на период исполнения.",
            ],
            "compliance_highlights": [
                "Нужно подтвердить соответствие каждой позиции ГОСТ, ТУ и характеристикам ТЗ."
            ],
        },
    )
    result = patch._decision_useful_preliminary(
        metadata={"analysis_mode": "production_llm_r10_1"},
        documents=_documents(),
    )

    highlights = "\n".join(result["contract_highlights"])
    assert "Проект контракта содержит условия оплаты." not in highlights
    assert "7 рабочих дней" in highlights
    assert "5 %" in highlights
    assert "ключевой ставки" in highlights
    assert "Цена контракта: твердая" in highlights
    compliance = "\n".join(result["compliance_highlights"])
    assert "ГОСТ 32511-2013" in compliance
    assert result["decision_useful_detail_count"] >= 9


def test_output_requirements_gain_exact_source_details(monkeypatch) -> None:
    analysis = extract_decision_useful_analysis(_documents())
    base_outputs = {
        "requirements": {
            "requirements": [
                {
                    "title": "Соответствие ГОСТ / ТУ",
                    "detail": "Товар должен соответствовать ГОСТ, ТУ и иной действующей нормативной документации.",
                    "type": "техническое требование",
                    "source": "Техническое задание",
                }
            ],
            "preliminary_analysis": {"decision_useful_analysis": analysis},
            "analysis_context": {},
        }
    }
    monkeypatch.setattr(
        patch,
        "_ORIGINAL_BUILD_OUTPUT_PAYLOADS",
        lambda *_args, **_kwargs: base_outputs,
    )

    outputs = patch._decision_useful_output_payloads(
        metadata={"analysis_mode": "production_llm_r10_1"}
    )
    rows = outputs["requirements"]["requirements"]
    joined = "\n".join(f"{row.get('title')} {row.get('detail')}" for row in rows)
    assert "ГОСТ 32511-2013" in joined
    assert "экологического класса К5" in joined
    assert "Требование к заявке / участнику" in joined

    context = outputs["requirements"]["analysis_context"]
    assert context["decision_useful_detail_count"] >= 9
    assert context["decision_useful_contract_coverage"]["payment"] is True
    assert context["decision_useful_contract_coverage"]["liability"] is True
    assert context["decision_useful_exact_standards"] == ["ГОСТ 32511-2013"]
    assert context["decision_useful_application_requirement_count"] >= 1
