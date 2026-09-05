from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from .contract import (
    CONTRACT_VERSION,
    BenchmarkContractError,
    canonical_sha256,
    source_bundle_sha256,
    validate_artifact,
    validate_case_manifest_consistency,
)


class ReviewState(StrEnum):
    AI_CURATED_SILVER = "AI_CURATED_SILVER"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    HUMAN_VERIFIED_GOLD = "HUMAN_VERIFIED_GOLD"


class WorkflowState(StrEnum):
    SOURCE_READY = "SOURCE_READY"
    EVALUATOR_BUNDLE_READY = "EVALUATOR_BUNDLE_READY"
    LABEL_FROZEN = "LABEL_FROZEN"
    SUT_ATTACHED = "SUT_ATTACHED"
    COMPARED = "COMPARED"
    REVIEWED = "REVIEWED"


FORBIDDEN_EVALUATOR_KEYS = {
    "analysis",
    "analysis_output",
    "artifact_refs",
    "comparison",
    "comparison_result",
    "extracted_fact",
    "extracted_facts",
    "normal_output",
    "rank",
    "ranking",
    "ranking_delta",
    "relevance_score",
    "report",
    "score",
    "scores",
    "score_reason",
    "score_reasons",
    "sut",
    "sut_output",
    "tender_agent",
    "tender_agent_output",
}

REVIEW_REASON_LOW_CONFIDENCE = "LOW_EVALUATOR_CONFIDENCE"
REVIEW_REASON_SOURCE_CONFLICT = "MATERIAL_SOURCE_CONFLICT"
REVIEW_REASON_WEAK_PROVENANCE = "WEAK_PROVENANCE"
REVIEW_REASON_SCHEMA = "SCHEMA_OR_CONSISTENCY_FAILURE"
REVIEW_REASON_UNCLASSIFIED = "UNCLASSIFIED_MATERIAL_DISAGREEMENT"
REVIEW_REASON_INSUFFICIENT = "MATERIAL_INSUFFICIENT_EVIDENCE"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise BenchmarkContractError("benchmark timestamps must include a timezone")
    return parsed


def _walk_forbidden_keys(value: Any, path: tuple[str, ...] = ()) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = key.lower().strip()
            child_path = path + (key,)
            if normalized in FORBIDDEN_EVALUATOR_KEYS:
                found.append(".".join(child_path))
            found.extend(_walk_forbidden_keys(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_walk_forbidden_keys(child, path + (str(index),)))
    return found


def assert_blind_evaluator_bundle(bundle: dict[str, Any]) -> None:
    validate_artifact("evaluator_bundle", bundle)
    forbidden = _walk_forbidden_keys(bundle)
    if forbidden:
        raise BenchmarkContractError(
            "SUT-derived keys are forbidden in evaluator bundle: " + ", ".join(forbidden)
        )
    expected = source_bundle_sha256(bundle["documents"])
    if bundle["source_bundle_sha256"] != expected:
        raise BenchmarkContractError("evaluator bundle source digest is inconsistent")


def prepare_evaluator_bundle(
    manifest: dict[str, Any],
    *,
    prepared_at: str | None = None,
) -> dict[str, Any]:
    validate_case_manifest_consistency(manifest)
    bundle = {
        "schema_version": CONTRACT_VERSION,
        "case_id": manifest["case_id"],
        "prepared_at": prepared_at or _utcnow(),
        "procurement": deepcopy(manifest["procurement"]),
        "source_urls": deepcopy(manifest["source_urls"]),
        "documents": deepcopy(manifest["documents"]),
        "source_scope": manifest["source_scope"],
        "source_bundle_sha256": manifest["source_bundle_sha256"],
        "case_manifest_sha256": canonical_sha256(manifest),
    }
    assert_blind_evaluator_bundle(bundle)
    return bundle


def _validate_evidence_refs(
    evaluator_bundle: dict[str, Any],
    discovery_label: dict[str, Any],
    document_truth: dict[str, Any],
) -> None:
    allowed_refs = set(evaluator_bundle["source_urls"])
    allowed_refs.update(document["path"] for document in evaluator_bundle["documents"])
    evidence_refs = list(discovery_label["evidence"])
    for fact in document_truth["facts"]:
        evidence_refs.extend(fact["evidence"])

    unknown = sorted(
        {
            evidence["source_ref"]
            for evidence in evidence_refs
            if evidence["source_ref"] not in allowed_refs
        }
    )
    if unknown:
        raise BenchmarkContractError(
            "blind labels contain evidence refs outside evaluator bundle: " + ", ".join(unknown)
        )
    if discovery_label["label"] != "UNCLEAR" and not discovery_label["evidence"]:
        raise BenchmarkContractError(
            "scored discovery labels require at least one source-grounded evidence ref"
        )
    for fact in document_truth["facts"]:
        if fact["abstention"] == "ASSERTED" and not fact["evidence"]:
            raise BenchmarkContractError(
                f"asserted document fact requires evidence: {fact['field']}"
            )


def validate_blind_label_consistency(
    evaluator_bundle: dict[str, Any],
    discovery_label: dict[str, Any],
    document_truth: dict[str, Any],
) -> None:
    assert_blind_evaluator_bundle(evaluator_bundle)
    validate_artifact("blind_discovery_label", discovery_label)
    validate_artifact("blind_document_truth", document_truth)

    case_ids = {
        evaluator_bundle["case_id"],
        discovery_label["case_id"],
        document_truth["case_id"],
    }
    if len(case_ids) != 1:
        raise BenchmarkContractError("evaluator bundle and blind labels refer to different cases")

    source_digests = {
        evaluator_bundle["source_bundle_sha256"],
        discovery_label["source_bundle_sha256"],
        document_truth["source_bundle_sha256"],
    }
    if len(source_digests) != 1:
        raise BenchmarkContractError("evaluator bundle and blind labels use different source bundles")

    fields = [fact["field"] for fact in document_truth["facts"]]
    if len(fields) != len(set(fields)):
        raise BenchmarkContractError("blind_document_truth contains duplicate fact fields")

    _validate_evidence_refs(evaluator_bundle, discovery_label, document_truth)


def freeze_blind_labels(
    evaluator_bundle: dict[str, Any],
    discovery_label: dict[str, Any],
    document_truth: dict[str, Any],
    *,
    frozen_at: str | None = None,
) -> dict[str, Any]:
    validate_blind_label_consistency(evaluator_bundle, discovery_label, document_truth)
    frozen_at = frozen_at or _utcnow()

    prepared = _parse_time(evaluator_bundle["prepared_at"])
    discovery_evaluated = _parse_time(discovery_label["evaluated_at"])
    truth_evaluated = _parse_time(document_truth["evaluated_at"])
    frozen = _parse_time(frozen_at)
    if discovery_evaluated < prepared or truth_evaluated < prepared:
        raise BenchmarkContractError(
            "blind labels must be created after the blind evaluator bundle is prepared"
        )
    if discovery_evaluated > frozen or truth_evaluated > frozen:
        raise BenchmarkContractError("blind labels cannot be frozen before evaluation completes")

    label_hashes = {
        "discovery_label_sha256": canonical_sha256(discovery_label),
        "document_truth_sha256": canonical_sha256(document_truth),
    }
    receipt = {
        "schema_version": CONTRACT_VERSION,
        "case_id": evaluator_bundle["case_id"],
        "frozen_at": frozen_at,
        "source_bundle_sha256": evaluator_bundle["source_bundle_sha256"],
        "evaluator_bundle_sha256": canonical_sha256(evaluator_bundle),
        "case_manifest_sha256": evaluator_bundle["case_manifest_sha256"],
        **label_hashes,
        "label_set_sha256": canonical_sha256(label_hashes),
    }
    validate_artifact("frozen_label", receipt)
    return receipt


def verify_frozen_labels(
    freeze_receipt: dict[str, Any],
    evaluator_bundle: dict[str, Any],
    discovery_label: dict[str, Any],
    document_truth: dict[str, Any],
) -> None:
    validate_artifact("frozen_label", freeze_receipt)
    validate_blind_label_consistency(evaluator_bundle, discovery_label, document_truth)

    if freeze_receipt["case_id"] != evaluator_bundle["case_id"]:
        raise BenchmarkContractError("freeze receipt case_id does not match blind artifacts")
    if freeze_receipt["source_bundle_sha256"] != evaluator_bundle["source_bundle_sha256"]:
        raise BenchmarkContractError("freeze receipt source bundle does not match blind artifacts")
    if freeze_receipt["case_manifest_sha256"] != evaluator_bundle["case_manifest_sha256"]:
        raise BenchmarkContractError("case manifest binding changed after blind-label freeze")
    if canonical_sha256(evaluator_bundle) != freeze_receipt["evaluator_bundle_sha256"]:
        raise BenchmarkContractError("evaluator bundle changed after blind-label freeze")
    if canonical_sha256(discovery_label) != freeze_receipt["discovery_label_sha256"]:
        raise BenchmarkContractError("blind discovery label changed after freeze")
    if canonical_sha256(document_truth) != freeze_receipt["document_truth_sha256"]:
        raise BenchmarkContractError("blind document truth changed after freeze")

    expected_label_set = canonical_sha256(
        {
            "discovery_label_sha256": freeze_receipt["discovery_label_sha256"],
            "document_truth_sha256": freeze_receipt["document_truth_sha256"],
        }
    )
    if freeze_receipt["label_set_sha256"] != expected_label_set:
        raise BenchmarkContractError("freeze receipt label-set digest is inconsistent")


def verify_sut_after_freeze(
    sut_ref: dict[str, Any],
    normalized_sut_output: dict[str, Any],
    freeze_receipt: dict[str, Any],
) -> None:
    validate_artifact("tender_agent_output_ref", sut_ref)
    validate_artifact("normalized_sut_output", normalized_sut_output)
    validate_artifact("frozen_label", freeze_receipt)

    case_ids = {
        sut_ref["case_id"],
        normalized_sut_output["case_id"],
        freeze_receipt["case_id"],
    }
    if len(case_ids) != 1:
        raise BenchmarkContractError("Tender Agent output belongs to a different case")

    source_digests = {
        sut_ref["source_bundle_sha256"],
        normalized_sut_output["source_bundle_sha256"],
        freeze_receipt["source_bundle_sha256"],
    }
    if len(source_digests) != 1:
        raise BenchmarkContractError("Tender Agent output used a different source bundle")

    if sut_ref["label_set_sha256_at_generation"] != freeze_receipt["label_set_sha256"]:
        raise BenchmarkContractError(
            "Tender Agent output was not bound to the frozen blind label set"
        )
    if canonical_sha256(normalized_sut_output) != sut_ref["normalized_output_sha256"]:
        raise BenchmarkContractError(
            "normalized Tender Agent output digest does not match tender_agent_output_ref"
        )

    frozen_at = _parse_time(freeze_receipt["frozen_at"])
    produced_at = _parse_time(sut_ref["produced_at"])
    if produced_at <= frozen_at:
        raise BenchmarkContractError(
            "Tender Agent output must be produced strictly after blind-label freeze"
        )


def _weak_provenance(
    discovery_label: dict[str, Any],
    document_truth: dict[str, Any],
) -> bool:
    if discovery_label["label"] != "UNCLEAR" and not discovery_label["evidence"]:
        return True
    return any(
        fact["materiality"] == "MATERIAL"
        and fact["abstention"] == "ASSERTED"
        and not fact["evidence"]
        for fact in document_truth["facts"]
    )


def route_review(
    manifest: dict[str, Any],
    discovery_label: dict[str, Any],
    document_truth: dict[str, Any],
    freeze_receipt: dict[str, Any],
    comparison_result: dict[str, Any],
    *,
    confidence_threshold: float = 0.80,
    updated_at: str | None = None,
) -> dict[str, Any]:
    validate_case_manifest_consistency(manifest)
    validate_artifact("blind_discovery_label", discovery_label)
    validate_artifact("blind_document_truth", document_truth)
    validate_artifact("frozen_label", freeze_receipt)
    validate_artifact("comparison_result", comparison_result)
    if not 0 <= confidence_threshold <= 1:
        raise BenchmarkContractError("confidence_threshold must be in [0, 1]")

    case_ids = {
        manifest["case_id"],
        discovery_label["case_id"],
        document_truth["case_id"],
        freeze_receipt["case_id"],
        comparison_result["case_id"],
    }
    if len(case_ids) != 1:
        raise BenchmarkContractError("review artifacts refer to different cases")
    if freeze_receipt["source_bundle_sha256"] != manifest["source_bundle_sha256"]:
        raise BenchmarkContractError("review source bundle does not match frozen source bundle")
    if canonical_sha256(manifest) != freeze_receipt["case_manifest_sha256"]:
        raise BenchmarkContractError("case manifest changed after blind-label freeze")
    if discovery_label["source_bundle_sha256"] != manifest["source_bundle_sha256"]:
        raise BenchmarkContractError("discovery label source bundle does not match manifest")
    if document_truth["source_bundle_sha256"] != manifest["source_bundle_sha256"]:
        raise BenchmarkContractError("document truth source bundle does not match manifest")

    reasons: set[str] = set()
    confidences = [float(discovery_label["confidence"]), float(document_truth["confidence"])]
    confidences.extend(
        float(fact["confidence"])
        for fact in document_truth["facts"]
        if fact["materiality"] == "MATERIAL"
    )
    if confidences and min(confidences) < confidence_threshold:
        reasons.add(REVIEW_REASON_LOW_CONFIDENCE)

    if manifest.get("source_conflict", False) or any(
        fact["materiality"] == "MATERIAL" and fact["abstention"] == "CONFLICTING_EVIDENCE"
        for fact in document_truth["facts"]
    ):
        reasons.add(REVIEW_REASON_SOURCE_CONFLICT)

    if not manifest.get("provenance_sufficient", True) or _weak_provenance(
        discovery_label, document_truth
    ):
        reasons.add(REVIEW_REASON_WEAK_PROVENANCE)

    if discovery_label["label"] == "UNCLEAR" or any(
        fact["materiality"] == "MATERIAL"
        and fact["abstention"] in {"UNKNOWN", "INSUFFICIENT_EVIDENCE"}
        for fact in document_truth["facts"]
    ):
        reasons.add(REVIEW_REASON_INSUFFICIENT)

    reasons.update(comparison_result.get("review_reasons", []))
    if comparison_result.get("schema_valid") is False:
        reasons.add(REVIEW_REASON_SCHEMA)

    state = ReviewState.NEEDS_REVIEW if reasons else ReviewState.AI_CURATED_SILVER
    review = {
        "schema_version": CONTRACT_VERSION,
        "case_id": manifest["case_id"],
        "state": state.value,
        "reasons": sorted(reasons),
        "updated_at": updated_at or _utcnow(),
        "reviewer": {"type": "SYSTEM", "id": "benchmark-pipeline"},
    }
    validate_artifact("review_state", review)
    return review


def route_failure(
    case_id: str,
    *,
    reason: str = REVIEW_REASON_SCHEMA,
    updated_at: str | None = None,
) -> dict[str, Any]:
    review = {
        "schema_version": CONTRACT_VERSION,
        "case_id": case_id,
        "state": ReviewState.NEEDS_REVIEW.value,
        "reasons": [reason],
        "updated_at": updated_at or _utcnow(),
        "reviewer": {"type": "SYSTEM", "id": "benchmark-pipeline"},
    }
    validate_artifact("review_state", review)
    return review


def promote_to_gold(
    review_state: dict[str, Any],
    *,
    reviewer_id: str,
    approval_note: str,
    updated_at: str | None = None,
) -> dict[str, Any]:
    validate_artifact("review_state", review_state)
    if review_state["state"] == ReviewState.HUMAN_VERIFIED_GOLD.value:
        raise BenchmarkContractError("benchmark case is already human-verified gold")
    if not reviewer_id.strip() or not approval_note.strip():
        raise BenchmarkContractError(
            "explicit Product Owner reviewer_id and approval_note are required"
        )
    promoted = {
        "schema_version": CONTRACT_VERSION,
        "case_id": review_state["case_id"],
        "state": ReviewState.HUMAN_VERIFIED_GOLD.value,
        "reasons": [],
        "updated_at": updated_at or _utcnow(),
        "reviewer": {"type": "PRODUCT_OWNER", "id": reviewer_id},
        "previous_state": review_state["state"],
        "approval_note": approval_note,
    }
    validate_artifact("review_state", promoted)
    return promoted


@dataclass
class BenchmarkCaseWorkflow:
    manifest: dict[str, Any]
    confidence_threshold: float = 0.80
    state: WorkflowState = field(init=False, default=WorkflowState.SOURCE_READY)
    _evaluator_bundle: dict[str, Any] | None = field(init=False, default=None)
    _discovery_label: dict[str, Any] | None = field(init=False, default=None)
    _document_truth: dict[str, Any] | None = field(init=False, default=None)
    _freeze_receipt: dict[str, Any] | None = field(init=False, default=None)
    _sut_ref: dict[str, Any] | None = field(init=False, default=None)
    _sut_output: dict[str, Any] | None = field(init=False, default=None)
    comparison_result: dict[str, Any] | None = field(init=False, default=None)
    review_state: dict[str, Any] | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        self.manifest = deepcopy(self.manifest)
        validate_case_manifest_consistency(self.manifest)
        if not 0 <= self.confidence_threshold <= 1:
            raise BenchmarkContractError("confidence_threshold must be in [0, 1]")

    @property
    def case_id(self) -> str:
        return self.manifest["case_id"]

    @property
    def freeze_receipt(self) -> dict[str, Any] | None:
        return deepcopy(self._freeze_receipt)

    @property
    def document_truth(self) -> dict[str, Any] | None:
        return deepcopy(self._document_truth)

    def evaluator_bundle(self, *, prepared_at: str | None = None) -> dict[str, Any]:
        if self.state not in {
            WorkflowState.SOURCE_READY,
            WorkflowState.EVALUATOR_BUNDLE_READY,
        }:
            raise BenchmarkContractError(
                "evaluator bundle is unavailable after blind labels are frozen"
            )
        if self._evaluator_bundle is None:
            self._evaluator_bundle = prepare_evaluator_bundle(
                self.manifest,
                prepared_at=prepared_at,
            )
            self.state = WorkflowState.EVALUATOR_BUNDLE_READY
        return deepcopy(self._evaluator_bundle)

    def freeze_labels(
        self,
        *,
        discovery_label: dict[str, Any],
        document_truth: dict[str, Any],
        frozen_at: str | None = None,
    ) -> dict[str, Any]:
        if self.state is not WorkflowState.EVALUATOR_BUNDLE_READY or self._evaluator_bundle is None:
            raise BenchmarkContractError(
                "blind labels can only be frozen after preparing the evaluator bundle"
            )
        self._discovery_label = deepcopy(discovery_label)
        self._document_truth = deepcopy(document_truth)
        self._freeze_receipt = freeze_blind_labels(
            self._evaluator_bundle,
            self._discovery_label,
            self._document_truth,
            frozen_at=frozen_at,
        )
        self.state = WorkflowState.LABEL_FROZEN
        return deepcopy(self._freeze_receipt)

    def attach_sut_output(
        self,
        *,
        output_ref: dict[str, Any],
        normalized_output: dict[str, Any],
    ) -> None:
        if self.state is not WorkflowState.LABEL_FROZEN or self._freeze_receipt is None:
            raise BenchmarkContractError(
                "Tender Agent output may only be attached after independent labels are frozen"
            )
        verify_sut_after_freeze(output_ref, normalized_output, self._freeze_receipt)
        self._sut_ref = deepcopy(output_ref)
        self._sut_output = deepcopy(normalized_output)
        self.state = WorkflowState.SUT_ATTACHED

    def compare(self, *, compared_at: str | None = None) -> dict[str, Any]:
        if self.state is not WorkflowState.SUT_ATTACHED:
            raise BenchmarkContractError("comparison requires frozen labels and attached SUT output")
        assert self._evaluator_bundle is not None
        assert self._discovery_label is not None
        assert self._document_truth is not None
        assert self._freeze_receipt is not None
        assert self._sut_ref is not None
        assert self._sut_output is not None

        from .comparator import compare_case

        self.comparison_result = compare_case(
            discovery_label=self._discovery_label,
            document_truth=self._document_truth,
            evaluator_bundle=self._evaluator_bundle,
            freeze_receipt=self._freeze_receipt,
            sut_ref=self._sut_ref,
            sut_output=self._sut_output,
            compared_at=compared_at or _utcnow(),
        )
        self.review_state = route_review(
            self.manifest,
            self._discovery_label,
            self._document_truth,
            self._freeze_receipt,
            self.comparison_result,
            confidence_threshold=self.confidence_threshold,
            updated_at=compared_at or _utcnow(),
        )
        self.state = WorkflowState.COMPARED
        return deepcopy(self.comparison_result)

    def promote_to_gold(
        self,
        *,
        reviewer_id: str,
        approval_note: str,
        updated_at: str | None = None,
    ) -> dict[str, Any]:
        if self.state is not WorkflowState.COMPARED or self.review_state is None:
            raise BenchmarkContractError("gold promotion requires a completed comparison")
        self.review_state = promote_to_gold(
            self.review_state,
            reviewer_id=reviewer_id,
            approval_note=approval_note,
            updated_at=updated_at,
        )
        self.state = WorkflowState.REVIEWED
        return deepcopy(self.review_state)
