from __future__ import annotations

from quality_gates.arv001.decision_usefulness import evaluate_decision_usefulness


def test_complete_10_6_summary_without_embedded_logical_list_still_checks_all_material_groups() -> None:
    summary = {
        "status": "complete",
        "analysis_allowed": True,
        "physical_file_count": 10,
        "logical_document_count": 6,
    }
    result = evaluate_decision_usefulness(
        {
            "technical": {"standards": [], "specific_clauses": []},
            "contract": {
                "payment": [],
                "security": [],
                "acceptance": [],
                "liability": [],
                "liability_cap": [],
                "liability_cap_status": "not_checked",
            },
            "application_requirements": [],
        },
        summary,
    )

    assert result["status"] == "FAIL"
    assert set(result["checks"]["document_kinds_checked"]) == {
        "technical_specification",
        "application_requirements",
        "contract_draft",
        "contract_performance_security",
    }
    blockers = set(result["blockers"])
    assert "technical_document_present_but_no_specific_standard_or_characteristic" in blockers
    assert "contract_present_but_payment_mechanics_not_extracted" in blockers
    assert "contract_present_but_acceptance_mechanics_not_extracted" in blockers
    assert "contract_present_but_liability_formula_not_extracted" in blockers
    assert "security_document_present_but_security_size_not_extracted" in blockers
    assert "security_document_present_but_security_form_not_extracted" in blockers
    assert "application_document_present_but_requirements_not_extracted" in blockers


def test_document_kind_aliases_and_names_are_recognized() -> None:
    summary = {
        "logical_documents": [
            {"document_kind": "technical_spec", "name": "Описание объекта закупки"},
            {"kind": "application", "name": "Требования к составу заявки"},
            {"role": "contract_draft", "name": "Проект контракта"},
            {
                "type": "обеспечение исполнения контракта",
                "name": "Реквизиты для обеспечения исполнения контракта",
            },
        ]
    }
    result = evaluate_decision_usefulness(
        {
            "technical": {"standards": [], "specific_clauses": []},
            "contract": {
                "payment": [],
                "security": [],
                "acceptance": [],
                "liability": [],
                "liability_cap": [],
                "liability_cap_status": "not_checked",
            },
            "application_requirements": [],
        },
        summary,
    )
    assert set(result["checks"]["document_kinds_checked"]) == {
        "technical_specification",
        "application_requirements",
        "contract_draft",
        "contract_performance_security",
    }
    assert result["status"] == "FAIL"
