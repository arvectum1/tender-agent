"""Final D07 semantic-scope binding for serialized tender outputs.

D07 establishes a provenance-backed procurement scope in the canonical
classifier. Older D04 compatibility/output wrappers still expose fallback
categories intended for GOODS/SERVICES/WORKS presentation. This final binding
keeps the canonical D07 scope authoritative at the serialized requirements
boundary without changing source extraction, evidence binding, or external
action behavior.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from src.modules.tender_operator_agent_demo import upload_service_legacy as _legacy

_INSTALLED = False
_ORIGINAL_OUTPUT_PAYLOADS: Any = None

# These D07 scopes are not safely representable by the older fallback category
# heuristic. GOODS/SERVICES/WORKS already serialize correctly and are therefore
# left untouched to minimize compatibility risk.
_AUTHORITATIVE_D07_SCOPES = {"rental", "mixed", "unresolved"}


def _classification_notice_text(metadata: dict[str, Any]) -> str:
    """Return the same stable notice/title input used by canonical D07 replay.

    Supporting documents can contain compatibility boilerplate (for example,
    generic service wording) that is not the procurement subject. The final
    serialization binding must therefore not reclassify on a different corpus
    than the canonical D07 decision that it is supposed to propagate.
    """

    return str(metadata.get("tender_title") or "")


def _bind_semantic_scope(outputs: dict[str, Any], *, metadata: dict[str, Any], documents: list[Any]) -> dict[str, Any]:
    scope = _legacy._classify_procurement_scope(
        metadata,
        documents,
        _classification_notice_text(metadata),
    )
    primary = str(scope.get("procurement_primary_scope") or "").strip().lower()
    if primary not in _AUTHORITATIVE_D07_SCOPES:
        return outputs

    requirements = outputs.get("requirements")
    if not isinstance(requirements, dict):
        return outputs

    preliminary = requirements.get("preliminary_analysis")
    if not isinstance(preliminary, dict):
        return outputs

    preliminary["procurement_kind"] = primary
    preliminary["scope"] = deepcopy(scope)

    context = requirements.get("analysis_context")
    if isinstance(context, dict):
        context["procurement_category"] = primary.upper()
        context["semantic_procurement_scope"] = deepcopy(scope)

    trace = outputs.get("trace")
    if isinstance(trace, dict):
        # Preserve legacy fallback_category as a compatibility field, but make
        # the semantic category explicit so it cannot be confused with the
        # authoritative D07 subject classification.
        trace["semantic_procurement_category"] = primary.upper()
        trace["semantic_procurement_scope"] = deepcopy(scope)

    return outputs


def _build_output_payloads(*args: Any, **kwargs: Any) -> dict[str, Any]:
    outputs = _ORIGINAL_OUTPUT_PAYLOADS(*args, **kwargs)
    metadata = kwargs.get("metadata")
    documents = kwargs.get("documents")
    if not isinstance(metadata, dict) or not isinstance(documents, list):
        return outputs
    return _bind_semantic_scope(outputs, metadata=metadata, documents=documents)


def install() -> None:
    """Install the D07 final-output binding exactly once and last."""

    global _INSTALLED, _ORIGINAL_OUTPUT_PAYLOADS
    if _INSTALLED:
        return
    _ORIGINAL_OUTPUT_PAYLOADS = _legacy._build_output_payloads
    _legacy._build_output_payloads = _build_output_payloads
    _INSTALLED = True
