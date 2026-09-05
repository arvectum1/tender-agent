"""BENCHMARK-PIPELINE-001 deterministic benchmark contract and workflow."""

from .comparator import aggregate_scorecard, compare_case
from .contracts import (
    ContractError,
    canonical_sha256,
    source_bundle_sha256,
    validate_artifact,
    validate_case_manifest_consistency,
)
from .workflow import (
    AntiCircularityError,
    freeze_labels,
    prepare_evaluator_bundle,
    promote_to_gold,
    route_failure,
    route_review,
    verify_frozen_labels,
)

__all__ = [
    "AntiCircularityError",
    "ContractError",
    "aggregate_scorecard",
    "canonical_sha256",
    "compare_case",
    "freeze_labels",
    "prepare_evaluator_bundle",
    "promote_to_gold",
    "route_failure",
    "route_review",
    "source_bundle_sha256",
    "validate_artifact",
    "validate_case_manifest_consistency",
    "verify_frozen_labels",
]
