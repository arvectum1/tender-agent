from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import Any


CONTRACT_VERSION = "1.0.0"


class BenchmarkContractError(ValueError):
    pass


class ReviewState(StrEnum):
    AI_CURATED_SILVER = "AI_CURATED_SILVER"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    HUMAN_VERIFIED_GOLD = "HUMAN_VERIFIED_GOLD"


DISCOVERY_LABELS = {"RELEVANT", "PARTIALLY_RELEVANT", "IRRELEVANT", "UNCLEAR"}
ABSTENTION_STATES = {"ASSERTED", "UNKNOWN", "INSUFFICIENT_EVIDENCE"}

_REQUIRED: dict[str, set[str]] = {
    "case_manifest": {
        "schema_version",
        "case_id",
        "procurement",
        "source_urls",
        "acquired_at",
        "documents",
        "source_scope",
    },
    "blind_discovery_label": {
        "schema_version",
        "case_id",
        "label",
        "reason",
        "confidence",
        "evidence",
        "frozen_at",
        "freeze_hash",
    },
    "blind_document_truth": {
        "schema_version",
        "case_id",
        "facts",
        "confidence",
        "frozen_at",
        "freeze_hash",
    },
    "tender_agent_output_ref": {
        "schema_version",
        "case_id",
        "runtime_version",
        "artifact_refs",
        "produced_at",
    },
    "comparison_result": {
        "schema_version",
        "case_id",
        "discovery",
        "document",
        "material_disagreement",
        "review_reasons",
    },
    "review_state": {
        "schema_version",
        "case_id",
        "state",
        "reasons",
        "updated_at",
        "reviewer",
    },
    "aggregate_scorecard": {
        "schema_version",
        "case_count",
        "discovery",
        "document",
        "review_states",
    },
}


def _require_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BenchmarkContractError(f"{name} must be an object")
    return value


def validate_artifact(kind: str, artifact: dict[str, Any]) -> dict[str, Any]:
    artifact = _require_mapping(artifact, kind)
    required = _REQUIRED.get(kind)
    if required is None:
        raise BenchmarkContractError(f"unknown benchmark artifact kind: {kind}")
    missing = sorted(required - set(artifact))
    if missing:
        raise BenchmarkContractError(f"{kind} missing required fields: {', '.join(missing)}")
    if artifact["schema_version"] != CONTRACT_VERSION:
        raise BenchmarkContractError(
            f"{kind}.schema_version must be {CONTRACT_VERSION}, got {artifact['schema_version']!r}"
        )

    if kind == "case_manifest":
        if not artifact["case_id"]:
            raise BenchmarkContractError("case_manifest.case_id must be non-empty")
        if not isinstance(artifact["source_urls"], list) or not artifact["source_urls"]:
            raise BenchmarkContractError("case_manifest.source_urls must be a non-empty array")
        if not isinstance(artifact["documents"], list):
            raise BenchmarkContractError("case_manifest.documents must be an array")
        for document in artifact["documents"]:
            _require_mapping(document, "case_manifest.documents[]")
            if not {"path", "sha256", "source_url"} <= set(document):
                raise BenchmarkContractError(
                    "each case_manifest document requires path, sha256 and source_url"
                )

    elif kind == "blind_discovery_label":
        if artifact["label"] not in DISCOVERY_LABELS:
            raise BenchmarkContractError("invalid discovery label")
        _validate_confidence(artifact["confidence"], "blind_discovery_label.confidence")
        if not isinstance(artifact["evidence"], list):
            raise BenchmarkContractError("blind_discovery_label.evidence must be an array")

    elif kind == "blind_document_truth":
        _validate_confidence(artifact["confidence"], "blind_document_truth.confidence")
        if not isinstance(artifact["facts"], list):
            raise BenchmarkContractError("blind_document_truth.facts must be an array")
        for fact in artifact["facts"]:
            _require_mapping(fact, "blind_document_truth.facts[]")
            if not {"field", "value", "evidence", "confidence", "abstention"} <= set(fact):
                raise BenchmarkContractError(
                    "each document truth fact requires field, value, evidence, confidence and abstention"
                )
            _validate_confidence(fact["confidence"], "fact.confidence")
            if fact["abstention"] not in ABSTENTION_STATES:
                raise BenchmarkContractError("invalid fact abstention state")
            if fact["abstention"] != "ASSERTED" and fact["value"] is not None:
                raise BenchmarkContractError("abstained facts must have null value")

    elif kind == "review_state":
        if artifact["state"] not in set(ReviewState):
            raise BenchmarkContractError("invalid review state")
        reviewer = _require_mapping(artifact["reviewer"], "review_state.reviewer")
        if not {"type", "id"} <= set(reviewer):
            raise BenchmarkContractError("reviewer requires type and id")

    return artifact


def _validate_confidence(value: Any, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
        raise BenchmarkContractError(f"{name} must be a number in [0, 1]")


def load_artifact(path: str | Path, kind: str) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        artifact = json.load(handle)
    return validate_artifact(kind, artifact)
