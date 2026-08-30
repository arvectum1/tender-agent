from __future__ import annotations

import pytest

from scripts.arv001.complete_corpus_contract import AcceptanceBlocked
from scripts.arv001.validate_decision_useful_candidate import (
    validate_rendered_material_terms,
)


def _analysis() -> dict:
    return {
        "technical": {
            "standards": ["ГОСТ 32511-2013"],
            "specific_clauses": [
                {"text": "Топливо дизельное зимнее экологического класса К5."}
            ],
        },
        "contract": {
            "payment": [
                {
                    "text": (
                        "Оплата осуществляется в течение 7 рабочих дней с даты "
                        "подписания документа о приемке. Аванс не предусмотрен."
                    )
                }
            ],
            "security": [
                {
                    "text": (
                        "Обеспечение исполнения составляет 5 % от цены Контракта "
                        "и предоставляется независимой гарантией."
                    )
                }
            ],
            "acceptance": [
                {
                    "text": (
                        "Приемка осуществляется в течение 5 рабочих дней с даты "
                        "поступления документа о приемке."
                    )
                }
            ],
            "liability": [
                {
                    "text": (
                        "Пеня составляет 1/300 ключевой ставки от не уплаченной "
                        "в срок суммы за каждый день просрочки."
                    )
                }
            ],
            "termination": [],
            "liability_cap": [
                {"text": "Общая сумма штрафов не может превышать цену Контракта."}
            ],
            "liability_cap_status": "found",
        },
        "application_requirements": [
            {"text": "Заявка должна содержать декларацию участника."}
        ],
    }


def _html() -> str:
    analysis = _analysis()
    values = [
        "ГОСТ 32511-2013",
        analysis["technical"]["specific_clauses"][0]["text"],
        analysis["contract"]["payment"][0]["text"],
        analysis["contract"]["security"][0]["text"],
        analysis["contract"]["acceptance"][0]["text"],
        analysis["contract"]["liability"][0]["text"],
        analysis["contract"]["liability_cap"][0]["text"],
        analysis["application_requirements"][0]["text"],
    ]
    return "<html><body>" + "".join(f"<p>{value}</p>" for value in values) + "</body></html>"


def test_render_validator_passes_when_all_material_groups_survive() -> None:
    result = validate_rendered_material_terms(_html(), _analysis())
    assert result["status"] == "PASS"
    assert result["exact_standard_count"] == 1
    assert result["contract_visible_counts"]["payment"] == 1
    assert result["liability_cap_status"] == "found"


def test_render_validator_allows_no_standard_when_gate_accepted_specific_technical_detail() -> None:
    analysis = _analysis()
    analysis["technical"]["standards"] = []
    rendered = _html().replace("<p>ГОСТ 32511-2013</p>", "")

    result = validate_rendered_material_terms(rendered, analysis)

    assert result["status"] == "PASS"
    assert result["exact_standard_count"] == 0
    assert result["technical_detail_count"] == 1


def test_render_validator_still_requires_extracted_standard_to_be_visible() -> None:
    with pytest.raises(
        AcceptanceBlocked,
        match="decision_useful_rendered_exact_standard_missing",
    ):
        validate_rendered_material_terms(
            _html().replace("<p>ГОСТ 32511-2013</p>", ""),
            _analysis(),
        )


def test_render_validator_fails_when_payment_is_lost() -> None:
    payment = _analysis()["contract"]["payment"][0]["text"]
    with pytest.raises(AcceptanceBlocked, match="decision_useful_rendered_payment_missing"):
        validate_rendered_material_terms(_html().replace(payment, ""), _analysis())


def test_render_validator_fails_when_application_requirement_is_lost() -> None:
    application = _analysis()["application_requirements"][0]["text"]
    with pytest.raises(
        AcceptanceBlocked,
        match="decision_useful_rendered_application_requirements_missing",
    ):
        validate_rendered_material_terms(_html().replace(application, ""), _analysis())


def test_render_validator_requires_explicit_cap_absence_state() -> None:
    analysis = _analysis()
    analysis["contract"]["liability_cap"] = []
    analysis["contract"]["liability_cap_status"] = "not_found_in_processed_contract_text"
    rendered = _html().replace(
        _analysis()["contract"]["liability_cap"][0]["text"],
        "Лимит штрафов / cap: отдельное ограничение общей суммы штрафов не найдено в обработанном тексте проекта контракта.",
    )
    result = validate_rendered_material_terms(rendered, analysis)
    assert result["liability_cap_status"] == "not_found_in_processed_contract_text"
