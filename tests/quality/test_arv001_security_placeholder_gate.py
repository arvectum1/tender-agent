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


def _analysis(security_text: str) -> dict:
    return {
        "technical": {
            "standards": ["ГОСТ 32511-2013"],
            "specific_clauses": [],
        },
        "contract": {
            "payment": [
                {
                    "text": (
                        "Оплата производится в течение 7 рабочих дней с даты "
                        "подписания документа о приемке."
                    )
                }
            ],
            "security": [{"text": security_text}],
            "acceptance": [
                {
                    "text": (
                        "Приемка проводится в течение 5 рабочих дней с даты "
                        "поступления документа о приемке."
                    )
                }
            ],
            "liability": [
                {
                    "text": (
                        "Пеня начисляется за каждый день просрочки в размере "
                        "1/300 ключевой ставки от не уплаченной в срок суммы."
                    )
                }
            ],
            "liability_cap": [],
            "liability_cap_status": "not_found_in_processed_contract_text",
        },
        "application_requirements": [
            {"text": "Заявка должна содержать декларацию участника."}
        ],
    }


def test_gate_accepts_explicit_blank_security_amount_as_source_uncertainty() -> None:
    analysis = _analysis(
        "Размер обеспечения исполнения Контракта устанавливается в соответствии "
        "с частями 6, 6.1, 6.2 статьи 96 ФЗ № 44 от начальной (максимальной) "
        "цены Контракта и составляет _______ руб. Обеспечение предоставляется "
        "независимой гарантией или внесением денежных средств."
    )

    result = evaluate_decision_usefulness(analysis, _summary())

    assert result["status"] == "PASS"
    assert result["blockers"] == []
    assert result["checks"]["security_size_status"] == "source_placeholder_unresolved"


def test_gate_still_rejects_security_form_with_no_amount_or_placeholder() -> None:
    analysis = _analysis(
        "Обеспечение исполнения Контракта предоставляется независимой гарантией "
        "или внесением денежных средств."
    )

    result = evaluate_decision_usefulness(analysis, _summary())

    assert result["status"] == "FAIL"
    assert (
        "security_document_present_but_security_size_not_extracted"
        in result["blockers"]
    )
    assert "security_document_present_but_security_form_not_extracted" not in result["blockers"]
    assert result["checks"]["security_size_status"] == "not_extracted"
