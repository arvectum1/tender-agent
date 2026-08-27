"""Fail-closed ARV-001 gate for decision-useful report granularity.

Evidence coverage alone is insufficient for a procurement decision report. If
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
    "проект контракта содержит",
)
_EXACT_STANDARD = re.compile(
    r"\b(?:ГОСТ(?:\s+Р)?\s+\d|ТР\s*ТС\s*\d|ТУ\s+\d)", re.IGNORECASE
)
_TECHNICAL_VALUE = re.compile(
    r"(?:\d|%|К[2-5]\b|евро\s*[-–]?\s*\d+|класс\w*\s+[А-ЯA-Z0-9-]+|"
    r"марка\w*\s+[А-ЯA-Z0-9-]+)",
    re.IGNORECASE,
)
_PAYMENT_MECHANICS = re.compile(
    r"(?:\d+\s*(?:рабоч\w*|календарн\w*)?\s*дн|\d+(?:[.,]\d+)?\s*%|"
    r"аванс\w*\s+не\s+предусмотр|аванс\w*|предоплат\w*|постоплат\w*)",
    re.IGNORECASE,
)
_PAYMENT_TRIGGER = re.compile(
    r"(?:с\s+дат\w*|после\s+(?:поставк\w*|при[её]мк\w*|подписани\w*|"
    r"предоставлени\w*)|документ\w*\s+о\s+при[её]мк\w*|акт\w*|сч[её]т\w*)",
    re.IGNORECASE,
)
_SECURITY_SIZE = re.compile(
    r"(?:\d+(?:[.,]\d+)?\s*%|\d[\d\s]*(?:[.,]\d+)?\s*руб|"
    r"не\s+(?:требуется|устанавливается|предусмотрено))",
    re.IGNORECASE,
)
_SECURITY_FORM = re.compile(
    r"(?:независим\w*\s+гарант\w*|банковск\w*\s+гарант\w*|"
    r"внесени\w*\s+денежн\w*\s+средств\w*|"
    r"денежн\w*\s+средств\w*\s+на\s+сч[её]т\w*|"
    r"не\s+(?:требуется|устанавливается|предусмотрено))",
    re.IGNORECASE,
)
_ACCEPTANCE_TIMING = re.compile(
    r"(?:\d+\s*(?:рабоч\w*|календарн\w*)?\s*дн|не\s+позднее|"
    r"в\s+течение|одновременно|в\s+момент)",
    re.IGNORECASE,
)
_ACCEPTANCE_TRIGGER = re.compile(
    r"(?:с\s+дат\w*|после\s+(?:поставк\w*|получени\w*|подписани\w*|"
    r"поступлени\w*)|документ\w*\s+о\s+при[её]мк\w*|акт\w*)",
    re.IGNORECASE,
)
_LIABILITY_RATE = re.compile(
    r"(?:\d+(?:[.,]\d+)?\s*%|\d+\s*процент|1\s*/\s*300|"
    r"одн\w*\s+тр[её]хсот\w*|ключев\w*\s+ставк\w*|"
    r"\d[\d\s]*(?:[.,]\d+)?\s*руб)",
    re.IGNORECASE,
)
_LIABILITY_BASE = re.compile(
    r"(?:от\s+(?:цен\w*|стоимост\w*|сумм\w*)|"
    r"не\s+уплаченн\w*\s+в\s+срок\s+сумм\w*|за\s+кажд\w*\s+день)",
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


def _joined(rows: list[dict[str, Any]]) -> str:
    return "\n".join(str(row.get("text") or "") for row in rows)


def evaluate_decision_usefulness(
    analysis: dict[str, Any], document_summary: dict[str, Any]
) -> dict[str, Any]:
    """Return PASS/FAIL and concrete blocking reasons for human-facing use."""

    kinds = _document_kinds(document_summary)
    technical = (
        analysis.get("technical") if isinstance(analysis.get("technical"), dict) else {}
    )
    contract = (
        analysis.get("contract") if isinstance(analysis.get("contract"), dict) else {}
    )
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
        material_technical = any(_EXACT_STANDARD.search(value) for value in standards) or bool(
            _TECHNICAL_VALUE.search(_joined(technical_rows))
        )
        if not material_technical:
            blockers.append(
                "technical_document_present_but_no_specific_standard_or_characteristic"
            )

    if "contract_draft" in kinds:
        payment_text = _joined(payment)
        if not payment or not _PAYMENT_MECHANICS.search(payment_text):
            blockers.append("contract_present_but_payment_mechanics_not_extracted")
        elif not _PAYMENT_TRIGGER.search(payment_text) and not re.search(
            r"аванс\w*\s+не\s+предусмотр", payment_text, re.IGNORECASE
        ):
            blockers.append("contract_payment_trigger_not_extracted")

        acceptance_text = _joined(acceptance)
        if not acceptance or not _ACCEPTANCE_TIMING.search(acceptance_text):
            blockers.append("contract_present_but_acceptance_mechanics_not_extracted")
        elif not _ACCEPTANCE_TRIGGER.search(acceptance_text):
            blockers.append("contract_acceptance_trigger_not_extracted")

        liability_text = _joined(liability)
        if not liability or not _LIABILITY_RATE.search(liability_text):
            blockers.append("contract_present_but_liability_formula_not_extracted")
        elif not _LIABILITY_BASE.search(liability_text):
            blockers.append("contract_liability_calculation_base_not_extracted")

        if cap_status not in {"found", "not_found_in_processed_contract_text"}:
            blockers.append("liability_cap_not_assessed")
        if cap_status == "found" and not cap:
            blockers.append("liability_cap_claimed_found_without_clause")

    if "contract_performance_security" in kinds:
        security_text = _joined(security)
        if not security or not _SECURITY_SIZE.search(security_text):
            blockers.append("security_document_present_but_security_size_not_extracted")
        if not security or not _SECURITY_FORM.search(security_text):
            blockers.append("security_document_present_but_security_form_not_extracted")

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
