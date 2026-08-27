from __future__ import annotations

from types import SimpleNamespace

from src.modules.tender_operator_agent_demo import decision_useful_output_patch as output_patch
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
            "Предельная температура фильтруемости — не выше минус 32 °C.",
        ),
        _doc(
            "contract_draft",
            "Проект контракта.docx",
            "Оплата поставленного товара осуществляется в течение 7 рабочих дней с даты подписания документа о приемке. Аванс не предусмотрен.\n"
            "Размер обеспечения исполнения Контракта составляет 5 % от цены Контракта.\n"
            "Приемка осуществляется в течение 5 рабочих дней с даты поступления документа о приемке.\n"
            "Пеня начисляется за каждый день просрочки в размере 1/300 ключевой ставки Центрального банка Российской Федерации от не уплаченной в срок суммы.\n"
            "Штраф составляет 1 процент цены Контракта.\n"
            "Общая сумма начисленных штрафов не может превышать цену Контракта.\n",
        ),
        _doc(
            "application_requirements",
            "Требования к составу заявки.docx",
            "Заявка должна содержать декларацию о соответствии участника единым требованиям.",
        ),
    ]


def test_liability_cap_is_explicitly_extracted() -> None:
    analysis = extract_decision_useful_analysis(_documents())
    contract = analysis["contract"]
    assert contract["liability_cap_status"] == "found"
    assert len(contract["liability_cap"]) == 1
    assert "не может превышать цену Контракта" in contract["liability_cap"][0]["text"]


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
