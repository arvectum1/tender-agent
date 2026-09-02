"""Expose persisted fallback provenance through the canonical run API.

PILOT-001-D04.2 correctly persisted source-bound fallback outputs, but the
canonical uploaded-run response rebuilt a narrow Pydantic projection and dropped
``requirements.json`` / ``trace.json``. Keep the legacy UI projection intact
while adding one additive machine-readable runtime contract for acceptance and
governance consumers.
"""

from typing import Any

from pydantic import Field

from src.modules.tender_operator_agent_demo import schemas as _schemas
from src.modules.tender_operator_agent_demo import upload_service_legacy as _legacy
from src.shared.types.common import APIModel


_INSTALLED = False
_ORIGINAL_GET_UPLOADED_DEMO_RUN: Any = None
_RUNTIME_ANALYSIS_SCHEMA_VERSION = "tender_operator_runtime_analysis_v1"


class TenderOperatorRuntimeAnalysisContract(APIModel):
    """Stable machine projection of persisted analysis provenance."""

    schema_version: str = _RUNTIME_ANALYSIS_SCHEMA_VERSION
    procurement_category: str | None = None
    grounding_policy: str | None = None
    fallback_category: str | None = None
    fallback_evidence_binding_policy: str | None = None
    fallback_evidence_binding_complete: bool | None = None
    evidence_map: dict[str, Any] = Field(default_factory=dict)
    requirements: list[dict[str, Any]] = Field(default_factory=list)
    analysis_context: dict[str, Any] = Field(default_factory=dict)
    trace: dict[str, Any] = Field(default_factory=dict)


class TenderOperatorUploadedRunResponse(
    _schemas.TenderOperatorUploadedRunResponse
):
    """Backward-compatible run response with persisted machine provenance."""

    runtime_analysis: TenderOperatorRuntimeAnalysisContract | None = None


# This model is installed dynamically during package initialization. Rebuild it
# while the concrete nested model is in scope so FastAPI/OpenAPI never sees an
# unresolved forward reference.
TenderOperatorUploadedRunResponse.model_rebuild(
    _types_namespace={
        "TenderOperatorRuntimeAnalysisContract": TenderOperatorRuntimeAnalysisContract,
    }
)


def _clean_category(value: Any) -> str | None:
    category = str(value or "").strip()
    return category.upper() if category else None


def _load_runtime_analysis(run_id: str) -> TenderOperatorRuntimeAnalysisContract | None:
    output_dir = _legacy.get_demo_run_output_dir(run_id)
    trace_path = output_dir / "trace.json"
    requirements_path = output_dir / "requirements.json"
    if not trace_path.is_file() or not requirements_path.is_file():
        return None

    try:
        trace = _legacy._read_json(trace_path)
        requirements_payload = _legacy._read_json(requirements_path)
    except (OSError, ValueError, TypeError):
        # The public read path must not turn a previously readable run into a
        # 500 solely because an optional machine projection is unavailable.
        return None

    if not isinstance(trace, dict) or not isinstance(requirements_payload, dict):
        return None

    rows = requirements_payload.get("requirements")
    if not isinstance(rows, list):
        rows = []
    requirement_rows = [dict(row) for row in rows if isinstance(row, dict)]

    analysis_context = requirements_payload.get("analysis_context")
    if not isinstance(analysis_context, dict):
        analysis_context = {}
    analysis_context = dict(analysis_context)

    fallback_category = _clean_category(trace.get("fallback_category"))
    procurement_category = fallback_category or _clean_category(
        analysis_context.get("procurement_category")
    )
    evidence_map = trace.get("evidence_map")
    if not isinstance(evidence_map, dict):
        evidence_map = {}

    return TenderOperatorRuntimeAnalysisContract(
        procurement_category=procurement_category,
        grounding_policy=(
            str(trace.get("grounding_policy")).strip()
            if trace.get("grounding_policy") is not None
            else None
        ),
        fallback_category=fallback_category,
        fallback_evidence_binding_policy=(
            str(trace.get("fallback_evidence_binding_policy")).strip()
            if trace.get("fallback_evidence_binding_policy") is not None
            else None
        ),
        fallback_evidence_binding_complete=(
            bool(trace.get("fallback_evidence_binding_complete"))
            if "fallback_evidence_binding_complete" in trace
            else None
        ),
        evidence_map=dict(evidence_map),
        requirements=requirement_rows,
        analysis_context=analysis_context,
        trace=dict(trace),
    )


def get_uploaded_demo_run(run_id: str) -> TenderOperatorUploadedRunResponse:
    """Return the legacy run projection plus persisted analysis provenance."""

    response = _ORIGINAL_GET_UPLOADED_DEMO_RUN(run_id)
    payload = response.model_dump(mode="json")
    runtime_analysis = _load_runtime_analysis(run_id)
    payload["runtime_analysis"] = (
        runtime_analysis.model_dump(mode="json") if runtime_analysis else None
    )
    return TenderOperatorUploadedRunResponse.model_validate(payload)


def install() -> None:
    """Install the additive runtime contract before facades/routers capture it."""

    global _INSTALLED
    global _ORIGINAL_GET_UPLOADED_DEMO_RUN
    if _INSTALLED:
        return

    _ORIGINAL_GET_UPLOADED_DEMO_RUN = _legacy.get_uploaded_demo_run

    # Router imports occur after package initialization. Replacing both schema
    # and legacy symbols makes FastAPI's response_model include runtime_analysis
    # instead of filtering the additive field away.
    _schemas.TenderOperatorUploadedRunResponse = TenderOperatorUploadedRunResponse
    _legacy.TenderOperatorUploadedRunResponse = TenderOperatorUploadedRunResponse
    _legacy.get_uploaded_demo_run = get_uploaded_demo_run
    _INSTALLED = True
