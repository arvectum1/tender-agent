from __future__ import annotations

from quality_gates.arv001.decision_usefulness import evaluate_decision_usefulness


def _summary() -> dict:
    return {
        "logical_documents": [
            {"kind": "technical_specification"},
            {"kind": "application_requirements"},
            {"kind": "contract_draft"},
            {"kind": "contract_performance_security"},
        ]
    }


def test_gate_rejects_generic_presence_only_report() -> None:
    analysis = {
        "technical": {"standards": [], "specific_clauses": []},
        "contract": {
            "payment": [{"text": "Проект контракта содержит условия оплаты."}],
            "security": [],
            "acceptance": [],
            "liability": [
                {"text": "Проект контракта содержит условия ответственности сторон."}
            ],
            "liability_cap": [],
            "liability_cap_status": "not_checked",
        },
        "application_requirements": [],
    }
    result = evaluate_decision_usefulness(analysis, _summary())
    assert result["status"] == "FAIL"
    assert (
        "technical_document_present_but_no_specific_standard_or_characteristic"
        in result["blockers"]
    )
    assert "contract_present_but_payment_mechanics_not_extracted" in result["blockers"]
    assert "contract_present_but_acceptance_mechanics_not_extracted" in result["blockers"]
    assert "contract_present_but_liability_formula_not_extracted" in result["blockers"]
    assert "liability_cap_not_assessed" in result["blockers"]
    assert "security_document_present_but_security_size_not_extracted" in result["blockers"]
    assert "security_document_present_but_security_form_not_extracted" in result["blockers"]
    assert "application_document_present_but_requirements_not_extracted" in result["blockers"]


def test_gate_accepts_concrete_material_terms_and_explicit_cap_absence() -> None:
    analysis = {
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
                        "подписания документа о приемке."
                    )
                }
            ],
            "security": [
                {
                    "text": (
                        "Размер обеспечения исполнения Контракта составляет 5 % "
                        "от цены Контракта. Обеспечение предоставляется независимой "
                        "гарантией или внесением денежных средств."
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
                        "Пеня начисляется за каждый день просрочки в размере 1/300 "
                        "ключевой ставки от не уплаченной в срок суммы."
                    )
                }
            ],
            "liability_cap": [],
            "liability_cap_status": "not_found_in_processed_contract_text",
        },
        "application_requirements": [
            {
                "text": (
                    "Заявка должна содержать декларацию о соответствии участника "
                    "единым требованиям."
                )
            }
        ],
    }
    result = evaluate_decision_usefulness(analysis, _summary())
    assert result["status"] == "PASS"
    assert result["blockers"] == []


def test_gate_rejects_amount_only_security_without_form() -> None:
    analysis = {
        "technical": {"standards": ["ГОСТ 32511-2013"], "specific_clauses": []},
        "contract": {
            "payment": [
                {
                    "text": (
                        "Оплата в течение 7 рабочих дней с даты подписания "
                        "документа о приемке."
                    )
                }
            ],
            "security": [
                {"text": "Размер обеспечения исполнения Контракта составляет 5 %."}
            ],
            "acceptance": [
                {
                    "text": (
                        "Приемка в течение 5 рабочих дней с даты поступления "
                        "документа о приемке."
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
            "liability_cap": [],
            "liability_cap_status": "not_found_in_processed_contract_text",
        },
        "application_requirements": [{"text": "Заявка должна содержать декларацию."}],
    }
    result = evaluate_decision_usefulness(analysis, _summary())
    assert result["status"] == "FAIL"
    assert "security_document_present_but_security_form_not_extracted" in result["blockers"]


def test_gate_requires_payment_and_acceptance_triggers() -> None:
    analysis = {
        "technical": {"standards": ["ГОСТ 32511-2013"], "specific_clauses": []},
        "contract": {
            "payment": [{"text": "Оплата производится в течение 7 рабочих дней."}],
            "security": [
                {
                    "text": (
                        "Обеспечение исполнения составляет 5 % и предоставляется "
                        "независимой гарантией."
                    )
                }
            ],
            "acceptance": [{"text": "Приемка проводится в течение 5 рабочих дней."}],
            "liability": [
                {
                    "text": (
                        "Пеня составляет 1/300 ключевой ставки от не уплаченной "
                        "в срок суммы за каждый день просрочки."
                    )
                }
            ],
            "liability_cap": [],
            "liability_cap_status": "not_found_in_processed_contract_text",
        },
        "application_requirements": [{"text": "Заявка должна содержать декларацию."}],
    }
    result = evaluate_decision_usefulness(analysis, _summary())
    assert result["status"] == "FAIL"
    assert "contract_payment_trigger_not_extracted" in result["blockers"]
    assert "contract_acceptance_trigger_not_extracted" in result["blockers"]


def test_gate_requires_cap_clause_when_cap_status_is_found() -> None:
    analysis = {
        "technical": {"standards": ["ГОСТ 32511-2013"], "specific_clauses": []},
        "contract": {
            "payment": [
                {
                    "text": (
                        "Оплата в течение 7 рабочих дней с даты подписания "
                        "документа о приемке."
                    )
                }
            ],
            "security": [
                {
                    "text": (
                        "Обеспечение исполнения — 5 %, независимая гарантия "
                        "или внесение денежных средств."
                    )
                }
            ],
            "acceptance": [
                {
                    "text": (
                        "Приемка в течение 5 рабочих дней с даты поступления "
                        "документа о приемке."
                    )
                }
            ],
            "liability": [
                {
                    "text": (
                        "Штраф составляет 1 процент от цены Контракта за "
                        "ненадлежащее исполнение обязательства."
                    )
                }
            ],
            "liability_cap": [],
            "liability_cap_status": "found",
        },
        "application_requirements": [{"text": "Заявка должна содержать декларацию."}],
    }
    result = evaluate_decision_usefulness(analysis, _summary())
    assert result["status"] == "FAIL"
    assert "liability_cap_claimed_found_without_clause" in result["blockers"]
