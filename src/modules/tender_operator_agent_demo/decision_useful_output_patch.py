"""Final output-payload binding for decision-useful R10.1 details."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from src.modules.tender_operator_agent_demo import decision_useful_runtime_patch as _runtime
from src.modules.tender_operator_agent_demo import upload_service_legacy as _legacy
from src.modules.tender_operator_agent_demo.decision_useful_extraction import material_detail_count
from src.modules.tender_operator_agent_demo.decision_useful_extraction_v2 import (
    extract_decision_useful_analysis,
)

_INSTALLED = False
_BASE_BUILD_OUTPUT_PAYLOADS = _legacy._build_output_payloads

_GENERIC_FLAGS = {
    "проект контракта содержит условия оплаты.",
    "проект контракта содержит условия ответственности сторон и штрафные санкции за нарушение обязательств.",
    "проект контракта содержит условия о штрафах, пенях или неустойке за нарушение обязательств.",
    "проект контракта содержит раздел об ответственности сторон.",
}


def _exact_contract_highlights(analysis: dict[str, Any]) -> list[str]:
    values = _runtime._contract_highlights(analysis)
    contract = analysis.get("contract") if isinstance(analysis.get("contract"), dict) else {}
    cap_rows = contract.get("liability_cap") or []
    for row in cap_rows:
        if not isinstance(row, dict) or not row.get("text"):
            continue
        source = str(row.get("source") or "Проект контракта")
        values.append(f"Лимит штрафов / cap: {row['text']} Источник: {source}.")
    if not cap_rows and any(contract.get(key) for key in ("liability", "payment", "acceptance", "security")):
        values.append(
            "Лимит штрафов / cap: отдельное ограничение общей суммы штрафов не найдено "
            "в обработанном тексте проекта контракта."
        )
    return values


def _inject_exact_requirements(outputs: dict[str, Any], analysis: dict[str, Any]) -> None:
    requirements_payload = outputs.get("requirements")
    if not isinstance(requirements_payload, dict):
        return
    preliminary = requirements_payload.get("preliminary_analysis")
    if not isinstance(preliminary, dict):
        return

    preliminary["decision_useful_analysis"] = deepcopy(analysis)
    preliminary["decision_useful_detail_count"] = material_detail_count(analysis)
    existing_contract = [
        str(value)
        for value in preliminary.get("contract_highlights", [])
        if str(value).strip().casefold() not in _GENERIC_FLAGS
        and not str(value).lower().startswith(
            ("оплата:", "обеспечение исполнения контракта:", "приёмка:", "ответственность /", "расторжение /", "лимит штрафов / cap:")
        )
    ]
    preliminary["contract_highlights"] = [
        *_exact_contract_highlights(analysis),
        *existing_contract,
    ][:30]

    _runtime._append_decision_useful_requirements(outputs)
    context = requirements_payload.get("analysis_context")
    if isinstance(context, dict):
        contract = analysis.get("contract") if isinstance(analysis.get("contract"), dict) else {}
        context["decision_useful_liability_cap_status"] = contract.get(
            "liability_cap_status", "not_checked"
        )
        context["decision_useful_liability_cap_count"] = len(
            contract.get("liability_cap") or []
        )


def _build_output_payloads(*args: Any, **kwargs: Any) -> dict[str, Any]:
    outputs = _BASE_BUILD_OUTPUT_PAYLOADS(*args, **kwargs)
    if kwargs.get("analysis_mode") != "production_llm_r10_1":
        return outputs
    analysis = extract_decision_useful_analysis(kwargs.get("documents") or [])
    _inject_exact_requirements(outputs, analysis)
    return outputs


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _legacy._build_output_payloads = _build_output_payloads
    _INSTALLED = True
