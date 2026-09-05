"""PILOT-001-D09: keep operator-facing output consistent with D07 scope.

D07 makes semantic procurement scope authoritative. Legacy D04 presentation
layers only understand GOODS/SERVICES/WORKS and may therefore render RENTAL,
MIXED or UNRESOLVED as services. This final presentation binding removes that
contradiction without changing extraction, evidence gates, or external actions.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from src.modules.tender_operator_agent_demo import upload_service_legacy as _legacy

_INSTALLED = False
_ORIGINAL_OUTPUT_PAYLOADS: Any = None
_NON_LEGACY_SCOPES = {"rental", "mixed", "unresolved"}


def _neutral_guidance(primary: str) -> list[str]:
    labels = {
        "rental": "аренды",
        "mixed": "смешанного предмета закупки",
        "unresolved": "неопределённого предмета закупки",
    }
    label = labels.get(primary, "предмета закупки")
    return [
        f"Проверить первичные документы и условия {label} вручную.",
        "Подтвердить существенные условия исполнения только по документам закупки.",
        "До принятия решения закрыть вопросы, помеченные как недостаточно подтверждённые.",
    ]


def _bind_operator_scope(outputs: dict[str, Any], *, metadata: dict[str, Any], documents: list[Any]) -> dict[str, Any]:
    scope = _legacy._classify_procurement_scope(metadata, documents, str(metadata.get("tender_title") or ""))
    primary = str(scope.get("procurement_primary_scope") or "").strip().lower()
    if primary not in _NON_LEGACY_SCOPES:
        return outputs

    requirements = outputs.get("requirements")
    if not isinstance(requirements, dict):
        return outputs
    preliminary = requirements.get("preliminary_analysis")
    if not isinstance(preliminary, dict):
        return outputs

    # Authoritative category and provenance-backed scope.
    preliminary["procurement_kind"] = primary
    preliminary["scope"] = deepcopy(scope)
    preliminary["grounded_fallback_category"] = primary.upper()

    canonical = preliminary.get("canonical_procurement_model")
    if isinstance(canonical, dict):
        canonical["procurement_scope"] = primary

    # Legacy category-specific prompts are unsafe for scopes that the old
    # renderer did not model. Fail closed with neutral, scope-aware guidance.
    preliminary["next_actions"] = _neutral_guidance(primary)

    context = requirements.get("analysis_context")
    if isinstance(context, dict):
        context["procurement_category"] = primary.upper()
        # Keep both the canonical operator-facing scope and the explicit
        # semantic scope aligned. Older payload builders may have left a
        # stale GOODS/SERVICES/WORKS-shaped procurement_scope here.
        context["procurement_scope"] = deepcopy(scope)
        context["semantic_procurement_scope"] = deepcopy(scope)

    trace = outputs.get("trace")
    if isinstance(trace, dict):
        trace["semantic_procurement_category"] = primary.upper()
        trace["semantic_procurement_scope"] = deepcopy(scope)
        if "fallback_category" in trace:
            trace["fallback_category"] = primary.upper()

    recommendation = outputs.get("final_recommendation")
    if isinstance(recommendation, dict):
        recommendation["recommendation"] = "manual_review_required"
        recommendation["label"] = "нужна ручная проверка"
        recommendation["rationale"] = [
            f"Категория закупки определена как {primary.upper()}, но специализированный автоматический анализ этой категории не подтверждён.",
            "Решение следует принимать по первичным документам и подтверждённым evidence-bound фактам.",
        ]
        recommendation["open_questions"] = [
            "Какие существенные условия предмета закупки подтверждены первичными документами?",
            "Какие условия исполнения требуют ручной проверки или уточнения у заказчика?",
            "Какие документы и подтверждения необходимы для решения об участии?",
        ]

    return outputs


def _build_output_payloads(*args: Any, **kwargs: Any) -> dict[str, Any]:
    outputs = _ORIGINAL_OUTPUT_PAYLOADS(*args, **kwargs)
    metadata = kwargs.get("metadata")
    documents = kwargs.get("documents")
    if not isinstance(metadata, dict) or not isinstance(documents, list):
        return outputs
    return _bind_operator_scope(outputs, metadata=metadata, documents=documents)


def install() -> None:
    """Install D09 after D07 as the final operator-output binding."""
    global _INSTALLED, _ORIGINAL_OUTPUT_PAYLOADS
    if _INSTALLED:
        return
    _ORIGINAL_OUTPUT_PAYLOADS = _legacy._build_output_payloads
    _legacy._build_output_payloads = _build_output_payloads
    _INSTALLED = True
