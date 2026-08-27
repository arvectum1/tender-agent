"""Install decision-useful extraction into the legacy-compatible report path.

The tender demo module already uses compatibility facades that wrap the legacy
implementation.  This patch is installed by the package before those facades
capture the legacy callables, so all later R10.1 calls receive concrete,
source-bound details without changing the historical provider protocol.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from src.modules.tender_operator_agent_demo import upload_service_legacy as _legacy
from src.modules.tender_operator_agent_demo.decision_useful_extraction import (
    extract_decision_useful_analysis,
    material_detail_count,
)

_INSTALLED = False
_ORIGINAL_PRELIMINARY = _legacy._build_preliminary_procurement_analysis
_ORIGINAL_BUILD_OUTPUT_PAYLOADS = _legacy._build_output_payloads

_GENERIC_CONTRACT_FLAGS = {
    "проект контракта содержит условия оплаты.",
    "проект контракта содержит условия ответственности сторон и штрафные санкции за нарушение обязательств.",
    "проект контракта содержит условия о штрафах, пенях или неустойке за нарушение обязательств.",
    "проект контракта содержит раздел об ответственности сторон.",
}
_CONTRACT_LABELS = {
    "payment": "Оплата",
    "security": "Обеспечение исполнения контракта",
    "acceptance": "Приёмка",
    "liability": "Ответственность / штрафы / пени",
    "termination": "Расторжение / односторонний отказ",
}


def _contract_highlights(analysis: dict[str, Any]) -> list[str]:
    contract = analysis.get("contract") if isinstance(analysis.get("contract"), dict) else {}
    result: list[str] = []
    seen: set[str] = set()
    for key in ("payment", "security", "acceptance", "liability", "termination"):
        label = _CONTRACT_LABELS[key]
        for row in contract.get(key) or []:
            if not isinstance(row, dict):
                continue
            text = " ".join(str(row.get("text") or "").split()).strip()
            source = " ".join(str(row.get("source") or "").split()).strip()
            if not text:
                continue
            value = f"{label}: {text}"
            if source:
                value += f" Источник: {source}."
            normalized = value.casefold()
            if normalized in seen:
                continue
            seen.add(normalized)
            result.append(value)
    return result


def _decision_useful_preliminary(**kwargs: Any) -> dict[str, Any]:
    result = _ORIGINAL_PRELIMINARY(**kwargs)
    metadata = kwargs.get("metadata")
    if not isinstance(metadata, dict) or metadata.get("analysis_mode") != "production_llm_r10_1":
        return result

    analysis = extract_decision_useful_analysis(kwargs.get("documents") or [])
    result = deepcopy(result)
    result["decision_useful_analysis"] = analysis
    result["decision_useful_detail_count"] = material_detail_count(analysis)

    existing = [
        str(item)
        for item in result.get("contract_highlights", [])
        if str(item).strip().casefold() not in _GENERIC_CONTRACT_FLAGS
    ]
    exact = _contract_highlights(analysis)
    # Exact source clauses are more useful than generic presence flags.  Keep
    # other deterministic legacy facts (for example fixed price) after them.
    result["contract_highlights"] = [*exact, *existing][:24]

    technical = analysis.get("technical") if isinstance(analysis.get("technical"), dict) else {}
    standards = [str(value) for value in technical.get("standards") or [] if value]
    specific = [
        str(row.get("text"))
        for row in technical.get("specific_clauses") or []
        if isinstance(row, dict) and row.get("text")
    ]
    if standards or specific:
        compliance = [
            item
            for item in result.get("compliance_highlights", [])
            if "соответств" not in str(item).lower() or not any(
                marker in str(item).lower() for marker in ("гост", "ту", "норматив")
            )
        ]
        result["compliance_highlights"] = [
            *[f"Точный стандарт из ТЗ: {value}." for value in standards],
            *specific,
            *compliance,
        ][:20]
    return result


def _requirement_identity(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        " ".join(str(row.get("title") or "").casefold().split()),
        " ".join(str(row.get("detail") or "").casefold().split()),
        " ".join(str(row.get("source") or "").casefold().split()),
    )


def _append_decision_useful_requirements(outputs: dict[str, Any]) -> None:
    requirements_payload = outputs.get("requirements")
    if not isinstance(requirements_payload, dict):
        return
    preliminary = requirements_payload.get("preliminary_analysis")
    if not isinstance(preliminary, dict):
        return
    analysis = preliminary.get("decision_useful_analysis")
    if not isinstance(analysis, dict):
        return

    rows = [
        dict(item) for item in requirements_payload.get("requirements", []) if isinstance(item, dict)
    ]
    seen = {_requirement_identity(row) for row in rows}
    technical = analysis.get("technical") if isinstance(analysis.get("technical"), dict) else {}

    additions: list[dict[str, str]] = []
    for standard in technical.get("standards") or []:
        additions.append(
            {
                "title": f"Стандарт / норматив: {standard}",
                "detail": str(standard),
                "type": "техническое требование",
                "source": "Техническое задание",
            }
        )
    for row in technical.get("specific_clauses") or []:
        if not isinstance(row, dict) or not row.get("text"):
            continue
        additions.append(
            {
                "title": "Конкретная характеристика из ТЗ",
                "detail": str(row["text"]),
                "type": "техническое требование",
                "source": str(row.get("source") or "Техническое задание"),
            }
        )
    for row in analysis.get("application_requirements") or []:
        if not isinstance(row, dict) or not row.get("text"):
            continue
        additions.append(
            {
                "title": "Требование к заявке / участнику",
                "detail": str(row["text"]),
                "type": "требование к заявке",
                "source": str(row.get("source") or "Требования к составу заявки"),
            }
        )

    for row in additions:
        identity = _requirement_identity(row)
        if identity in seen:
            continue
        seen.add(identity)
        rows.append(row)
    requirements_payload["requirements"] = rows

    context = requirements_payload.get("analysis_context")
    if isinstance(context, dict):
        contract = analysis.get("contract") if isinstance(analysis.get("contract"), dict) else {}
        context["decision_useful_detail_count"] = material_detail_count(analysis)
        context["decision_useful_contract_coverage"] = {
            key: bool(contract.get(key))
            for key in ("payment", "security", "acceptance", "liability", "termination")
        }
        context["decision_useful_exact_standards"] = list(technical.get("standards") or [])
        context["decision_useful_application_requirement_count"] = len(
            analysis.get("application_requirements") or []
        )


def _decision_useful_output_payloads(*args: Any, **kwargs: Any) -> dict[str, Any]:
    outputs = _ORIGINAL_BUILD_OUTPUT_PAYLOADS(*args, **kwargs)
    metadata = kwargs.get("metadata")
    if not isinstance(metadata, dict) or metadata.get("analysis_mode") != "production_llm_r10_1":
        return outputs
    _append_decision_useful_requirements(outputs)
    return outputs


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _legacy._build_preliminary_procurement_analysis = _decision_useful_preliminary
    _legacy._build_output_payloads = _decision_useful_output_payloads
    _INSTALLED = True
