"""Fail-closed ARV-001 gate for decision-useful report granularity.

Evidence coverage alone is insufficient for a procurement decision report.  If
substantive documents are present, the candidate must surface concrete material
terms rather than generic existence statements.
"""

from __future__ import annotations

import re
from typing import Any

_GENERIC_ONLY = (
    "содержит условия оплаты",
    "содержит условия ответственности",
    "соответствовать гост, ту",
    "соответствует гост, ту",
    "требуется ручная проверка",
)
_EXACT_STANDARD = re.compile(
    r"\b(?:ГОСТ(?:\s+Р)?\s+\d|ТР\s*ТС\s*\d|ТУ\s+\d)", re.IGNORECASE
)
_MATERIAL_NUMBER = re.compile(
    r"(?:\d|%|рабоч\w*\s+дн|календарн\w*\s+дн|аванс\w*\s+не\s+предусмотр)",
    re.IGNORECASE,
)


def _document_kinds(document_summary: dict[str, Any]) -> set[str]:
    return {
        str(item.get("kind") or "")
        for item in document_summary.get("logical_documents") or []
        if isinstance(item, dict)
    }


def _specific_rows(rows: list[Any]) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if isinstance(row, dict)
        and str(row.get("text") or "").strip()
        and not any(
            marker in str(row.get("text") or "").lower() for marker in _GENERIC_ONLY
        )
    ]


def evaluate_decision_usefulness(
    analysis: dict[str, Any], document_summary: dict[str, Any]
) -> dict[str, Any]:
    """Return PASS/FAIL and concrete blocking reasons for human-facing use."""

    kinds = _document_kinds(document_summary)
    technical = analysis.get("technical") if isinstance(analysis.get("technical"), dict) else {}
    contract = analysis.get("contract") if isinstance(analysis.get("contract"), dict) else {}
    application = _specific_rows(list(analysis.get("application_requirements") or []))

    standards = [str(value) for value in technical.get("standards") or [] if value]
    technical_rows = _specific_rows(list(technical.get("specific_clauses") or []))
    payment = _specific_rows(list(contract.get("payment") or []))
    security = _specific_rows(list(contract.get("security") or []))
    acceptance = _specific_rows(list(contract.get("acceptance") or []))
    liability = _specific_rows(list(contract.get("liability") or []))
    cap = _specific_rows(list(contract.get("liability_cap") or []))
    cap_status = str(contract.get("liability_cap_status") or "not_checked")

    blockers: list[str] = []
    if "technical_specification" in kinds:
        material_technical = any(_EXACT_STANDARD.search(value) for value in standards) or any(
            _MATERIAL_NUMBER.search(str(row.get("text") or "")) for row in technical_rows
        )
        if not material_technical:
            blockers.append("technical_document_present_but_no_specific_standard_or_characteristic")

    if "contract_draft" in kinds:
        if not payment or not any(_MATERIAL_NUMBER.search(str(row.get("text") or "")) for row in payment):
            blockers.append("contract_present_but_payment_mechanics_not_extracted")
        if not acceptance or not any(_MATERIAL_NUMBER.search(str(row.get("text") or "")) for row in acceptance):
            blockers.append("contract_present_but_acceptance_mechanics_not_extracted")
        if not liability or not any(_MATERIAL_NUMBER.search(str(row.get("text") or "")) for row in liability):
            blockers.append("contract_present_but_liability_formula_not_extracted")
        if cap_status not in {"found", "not_found_in_processed_contract_text"}:
            blockers.append("liability_cap_not_assessed")
        if cap_status == "found" and not cap:
            blockers.append("liability_cap_claimed_found_without_clause")

    if "contract_performance_security" in kinds and not security:
        blockers.append("security_document_present_but_security_terms_not_extracted")

    if "application_requirements" in kinds and not application:
        blockers.append("application_document_present_but_requirements_not_extracted")

    return {
        "status": "PASS" if not blockers else "FAIL",
        "blockers": blockers,
        "checks": {
            "exact_standard_count": len(standards),
            "technical_specific_clause_count": len(technical_rows),
            "payment_clause_count": len(payment),
            "security_clause_count": len(security),
            "acceptance_clause_count": len(acceptance),
            "liability_clause_count": len(liability),
            "liability_cap_status": cap_status,
            "application_requirement_count": len(application),
        },
    }
