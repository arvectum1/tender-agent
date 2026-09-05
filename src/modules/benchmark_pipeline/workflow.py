from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from .contract import CONTRACT_VERSION, BenchmarkContractError, ReviewState, validate_artifact


class WorkflowState(StrEnum):
    SOURCE_READY = "SOURCE_READY"
    LABEL_FROZEN = "LABEL_FROZEN"
    SUT_ATTACHED = "SUT_ATTACHED"
    COMPARED = "COMPARED"
    REVIEWED = "REVIEWED"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass
class BenchmarkCaseWorkflow:
    manifest: dict[str, Any]
    confidence_threshold: float = 0.8
    state: WorkflowState = field(init=False, default=WorkflowState.SOURCE_READY)
    discovery_label: dict[str, Any] | None = field(init=False, default=None)
    document_truth: dict[str, Any] | None = field(init=False, default=None)
    sut_output_ref: dict[str, Any] | None = field(init=False, default=None)
    comparison_result: dict[str, Any] | None = field(init=False, default=None)
    review_state: dict[str, Any] | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        validate_artifact("case_manifest", self.manifest)
        if not 0 <= self.confidence_threshold <= 1:
            raise BenchmarkContractError("confidence_threshold must be in [0, 1]")

    @property
    def case_id(self) -> str:
        return self.manifest["case_id"]

    def evaluator_bundle(self) -> dict[str, Any]:
        """Return the only bundle allowed for first-pass independent evaluation.

        It is deliberately reconstructed from the case manifest and cannot contain
        Tender Agent output, rankings, extracted facts, score reasons or comparator data.
        """
        if self.state is not WorkflowState.SOURCE_READY:
            raise BenchmarkContractError("evaluator bundle is only available before label freeze")
        return {
            "schema_version": CONTRACT_VERSION,
            "case_id": self.case_id,
            "procurement": self.manifest["procurement"],
            "source_urls": list(self.manifest["source_urls"]),
            "documents": [
                {
                    "path": doc["path"],
                    "sha256": doc["sha256"],
                    "source_url": doc["source_url"],
                }
                for doc in self.manifest["documents"]
            ],
            "source_scope": self.manifest["source_scope"],
        }

    def freeze_labels(
        self,
        *,
        discovery_label: dict[str, Any],
        document_truth: dict[str, Any],
        frozen_at: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if self.state is not WorkflowState.SOURCE_READY:
            raise BenchmarkContractError("blind labels can only be frozen once, before SUT output")
        frozen_at = frozen_at or _utcnow()

        discovery = dict(discovery_label)
        discovery.update(
            {
                "schema_version": CONTRACT_VERSION,
                "case_id": self.case_id,
                "frozen_at": frozen_at,
            }
        )
        discovery["freeze_hash"] = _canonical_hash(
            {k: v for k, v in discovery.items() if k != "freeze_hash"}
        )

        truth = dict(document_truth)
        truth.update(
            {
                "schema_version": CONTRACT_VERSION,
                "case_id": self.case_id,
                "frozen_at": frozen_at,
            }
        )
        truth["freeze_hash"] = _canonical_hash({k: v for k, v in truth.items() if k != "freeze_hash"})

        validate_artifact("blind_discovery_label", discovery)
        validate_artifact("blind_document_truth", truth)
        self.discovery_label = discovery
        self.document_truth = truth
        self.state = WorkflowState.LABEL_FROZEN
        return discovery, truth

    def attach_sut_output(self, output_ref: dict[str, Any]) -> dict[str, Any]:
        if self.state is not WorkflowState.LABEL_FROZEN:
            raise BenchmarkContractError(
                "Tender Agent output may only be attached after independent labels are frozen"
            )
        output = dict(output_ref)
        output.setdefault("schema_version", CONTRACT_VERSION)
        output.setdefault("case_id", self.case_id)
        validate_artifact("tender_agent_output_ref", output)
        self.sut_output_ref = output
        self.state = WorkflowState.SUT_ATTACHED
        return output

    def record_comparison(self, result: dict[str, Any]) -> dict[str, Any]:
        if self.state is not WorkflowState.SUT_ATTACHED:
            raise BenchmarkContractError("comparison requires frozen labels and attached SUT output")
        comparison = dict(result)
        comparison.setdefault("schema_version", CONTRACT_VERSION)
        comparison.setdefault("case_id", self.case_id)
        validate_artifact("comparison_result", comparison)
        self.comparison_result = comparison
        self.state = WorkflowState.COMPARED
        self.review_state = self._route_review()
        return comparison

    def _route_review(self) -> dict[str, Any]:
        assert self.discovery_label is not None
        assert self.document_truth is not None
        assert self.comparison_result is not None
        reasons: list[str] = []
        if self.discovery_label["confidence"] < self.confidence_threshold:
            reasons.append("LOW_DISCOVERY_CONFIDENCE")
        if self.document_truth["confidence"] < self.confidence_threshold:
            reasons.append("LOW_DOCUMENT_CONFIDENCE")
        if self.manifest.get("source_conflict"):
            reasons.append("UNRESOLVED_SOURCE_CONFLICT")
        if not self.manifest.get("provenance_sufficient", True):
            reasons.append("INSUFFICIENT_PROVENANCE")
        if self.comparison_result.get("material_disagreement"):
            reasons.append("MATERIAL_DISAGREEMENT")
        if self.comparison_result.get("schema_valid") is False:
            reasons.append("SCHEMA_VALIDATION_FAILURE")
        state = ReviewState.NEEDS_REVIEW if reasons else ReviewState.AI_CURATED_SILVER
        review = {
            "schema_version": CONTRACT_VERSION,
            "case_id": self.case_id,
            "state": state.value,
            "reasons": reasons,
            "updated_at": _utcnow(),
            "reviewer": {"type": "SYSTEM", "id": "benchmark-pipeline"},
        }
        validate_artifact("review_state", review)
        return review

    def promote_to_gold(self, *, reviewer_id: str, note: str = "") -> dict[str, Any]:
        if self.state is not WorkflowState.COMPARED or self.review_state is None:
            raise BenchmarkContractError("gold promotion requires a completed comparison")
        if not reviewer_id:
            raise BenchmarkContractError("Product Owner reviewer_id is required")
        self.review_state = {
            "schema_version": CONTRACT_VERSION,
            "case_id": self.case_id,
            "state": ReviewState.HUMAN_VERIFIED_GOLD.value,
            "reasons": [note] if note else [],
            "updated_at": _utcnow(),
            "reviewer": {"type": "PRODUCT_OWNER", "id": reviewer_id},
        }
        validate_artifact("review_state", self.review_state)
        self.state = WorkflowState.REVIEWED
        return self.review_state
