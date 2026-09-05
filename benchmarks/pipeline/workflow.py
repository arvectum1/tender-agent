from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from .contracts import (
    SCHEMA_VERSION,
    canonical_sha256,
    validate_artifact,
    validate_case_manifest_consistency,
)

FORBIDDEN_EVALUATOR_KEYS = {
    "comparison",
    "comparison_result",
    "extracted_fact",
    "extracted_facts",
    "normal_output",
    "ranking",
    "report",
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


class AntiCircularityError(ValueError):
    """Raised when system-under-test information can leak into blind evaluation."""


def _walk_keys(value: Any, path: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], str]]:
    found: list[tuple[tuple[str, ...], str]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = key.lower().strip()
            if normalized in FORBIDDEN_EVALUATOR_KEYS:
                found.append((path, key))
            found.extend(_walk_keys(child, path + (key,)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_walk_keys(child, path + (str(index),)))
    return found


def assert_blind_payload(payload: dict[str, Any]) -> None:
    forbidden = _walk_keys(payload)
    if forbidden:
        rendered = ", ".join(".".join((*path, key)) for path, key in forbidden)
        raise AntiCircularityError(f"SUT-derived keys are forbidden in evaluator bundle: {rendered}")


def prepare_evaluator_bundle(manifest: dict[str, Any], *, prepared_at: str) -> dict[str, Any]:
    """Create the only metadata bundle an independent evaluator receives before freeze."""
    validate_case_manifest_consistency(manifest)
    sources = []
    for source in manifest["sources"]:
        sources.append(
            {
                key: deepcopy(source[key])
                for key in (
                    "source_id",
                    "kind",
                    "title",
                    "public_url",
                    "retrieved_at",
                    "sha256",
                    "local_path",
                    "supersedes_source_id",
                )
                if key in source
            }
        )
    bundle = {
        "schema_version": SCHEMA_VERSION,
        "case_id": manifest["case_id"],
        "prepared_at": prepared_at,
        "source_bundle_sha256": manifest["source_bundle_sha256"],
        "sources": sources,
    }
    assert_blind_payload(bundle)
    validate_artifact("evaluator_bundle", bundle)
    return bundle


def freeze_labels(
    evaluator_bundle: dict[str, Any],
    discovery_label: dict[str, Any],
    document_truth: dict[str, Any],
    *,
    frozen_at: str,
) -> dict[str, Any]:
    validate_artifact("evaluator_bundle", evaluator_bundle)
    validate_artifact("blind_discovery_label", discovery_label)
    validate_artifact("blind_document_truth", document_truth)
    assert_blind_payload(evaluator_bundle)
    if discovery_label["case_id"] != document_truth["case_id"]:
        raise AntiCircularityError("blind labels refer to different case_id values")
    if evaluator_bundle["case_id"] != discovery_label["case_id"]:
        raise AntiCircularityError("evaluator bundle and blind labels refer to different cases")
    if discovery_label["source_bundle_sha256"] != document_truth["source_bundle_sha256"]:
        raise AntiCircularityError("blind labels refer to different source bundles")
    if evaluator_bundle["source_bundle_sha256"] != discovery_label["source_bundle_sha256"]:
        raise AntiCircularityError("evaluator bundle and blind labels refer to different source bundles")

    allowed_source_ids = {source["source_id"] for source in evaluator_bundle["sources"]}
    evidence_refs = list(discovery_label["evidence_refs"])
    for fact in document_truth["facts"]:
        evidence_refs.extend(fact["evidence_refs"])
    unknown_refs = sorted(
        {ref["source_id"] for ref in evidence_refs if ref["source_id"] not in allowed_source_ids}
    )
    if unknown_refs:
        raise AntiCircularityError(
            "blind labels contain evidence refs outside evaluator bundle: "
            + ", ".join(unknown_refs)
        )
    label_set = {
        "discovery_label_sha256": canonical_sha256(discovery_label),
        "document_truth_sha256": canonical_sha256(document_truth),
    }
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "case_id": discovery_label["case_id"],
        "frozen_at": frozen_at,
        "source_bundle_sha256": discovery_label["source_bundle_sha256"],
        "evaluator_bundle_sha256": canonical_sha256(evaluator_bundle),
        **label_set,
        "label_set_sha256": canonical_sha256(label_set),
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
    validate_artifact("evaluator_bundle", evaluator_bundle)
    assert_blind_payload(evaluator_bundle)
    validate_artifact("blind_discovery_label", discovery_label)
    validate_artifact("blind_document_truth", document_truth)
    expected = {
        "discovery_label_sha256": canonical_sha256(discovery_label),
        "document_truth_sha256": canonical_sha256(document_truth),
    }
    if (
        freeze_receipt["case_id"] != discovery_label["case_id"]
        or freeze_receipt["case_id"] != document_truth["case_id"]
        or freeze_receipt["case_id"] != evaluator_bundle["case_id"]
    ):
        raise AntiCircularityError("freeze receipt case_id does not match blind artifacts")
    if (
        freeze_receipt["source_bundle_sha256"] != discovery_label["source_bundle_sha256"]
        or freeze_receipt["source_bundle_sha256"] != evaluator_bundle["source_bundle_sha256"]
    ):
        raise AntiCircularityError("freeze receipt source bundle does not match blind artifacts")
    if canonical_sha256(evaluator_bundle) != freeze_receipt["evaluator_bundle_sha256"]:
        raise AntiCircularityError("evaluator bundle changed after blind-label freeze")
    if expected["discovery_label_sha256"] != freeze_receipt["discovery_label_sha256"]:
        raise AntiCircularityError("blind discovery label changed after freeze")
    if expected["document_truth_sha256"] != freeze_receipt["document_truth_sha256"]:
        raise AntiCircularityError("blind document truth changed after freeze")
    if canonical_sha256(expected) != freeze_receipt["label_set_sha256"]:
        raise AntiCircularityError("freeze receipt label-set digest is inconsistent")


def verify_sut_after_freeze(
    sut_ref: dict[str, Any],
    freeze_receipt: dict[str, Any],
) -> None:
    validate_artifact("tender_agent_output_ref", sut_ref)
    validate_artifact("frozen_label", freeze_receipt)
    if sut_ref["case_id"] != freeze_receipt["case_id"]:
        raise AntiCircularityError("Tender Agent output belongs to a different case")
    if sut_ref["source_bundle_sha256"] != freeze_receipt["source_bundle_sha256"]:
        raise AntiCircularityError("Tender Agent output used a different source bundle")
    if sut_ref["label_set_sha256_at_generation"] != freeze_receipt["label_set_sha256"]:
        raise AntiCircularityError("Tender Agent output was not bound to the frozen blind label set")
    frozen_at = datetime.fromisoformat(freeze_receipt["frozen_at"].replace("Z", "+00:00"))
    produced_at = datetime.fromisoformat(sut_ref["produced_at"].replace("Z", "+00:00"))
    if produced_at <= frozen_at:
        raise AntiCircularityError("Tender Agent output must be produced strictly after blind-label freeze")


def _has_weak_provenance(discovery_label: dict[str, Any], document_truth: dict[str, Any]) -> bool:
    if discovery_label["decision"] in {"RELEVANT", "NOT_RELEVANT"} and not discovery_label["evidence_refs"]:
        return True
    for fact in document_truth["facts"]:
        if fact["status"] == "ASSERTED" and fact["materiality"] == "MATERIAL" and not fact["evidence_refs"]:
            return True
    return False


def route_review(
    comparison: dict[str, Any],
    discovery_label: dict[str, Any],
    document_truth: dict[str, Any],
    *,
    routed_at: str,
    confidence_threshold: float = 0.80,
) -> dict[str, Any]:
    """Route benchmark curation state. SUT failure alone does not invalidate a sound label."""
    validate_artifact("comparison_result", comparison)
    validate_artifact("blind_discovery_label", discovery_label)
    validate_artifact("blind_document_truth", document_truth)

    reasons: set[str] = set()
    confidences = [float(discovery_label["confidence"])]
    confidences.extend(float(fact["confidence"]) for fact in document_truth["facts"])
    if confidences and min(confidences) < confidence_threshold:
        reasons.add(REVIEW_REASON_LOW_CONFIDENCE)

    if any(
        fact["materiality"] == "MATERIAL" and fact["status"] == "CONFLICTING_EVIDENCE"
        for fact in document_truth["facts"]
    ):
        reasons.add(REVIEW_REASON_SOURCE_CONFLICT)

    if _has_weak_provenance(discovery_label, document_truth):
        reasons.add(REVIEW_REASON_WEAK_PROVENANCE)

    if comparison["schema_failures"]:
        reasons.add(REVIEW_REASON_SCHEMA)

    if discovery_label["decision"] in {"UNKNOWN", "INSUFFICIENT_EVIDENCE"}:
        reasons.add(REVIEW_REASON_INSUFFICIENT)
    if any(
        fact["materiality"] == "MATERIAL"
        and fact["status"] in {"UNKNOWN", "INSUFFICIENT_EVIDENCE"}
        for fact in document_truth["facts"]
    ):
        reasons.add(REVIEW_REASON_INSUFFICIENT)

    if REVIEW_REASON_UNCLASSIFIED in comparison["review_signals"]:
        reasons.add(REVIEW_REASON_UNCLASSIFIED)

    state = "NEEDS_REVIEW" if reasons else "AI_CURATED_SILVER"
    review = {
        "schema_version": SCHEMA_VERSION,
        "case_id": comparison["case_id"],
        "state": state,
        "reasons": sorted(reasons),
        "routed_at": routed_at,
        "requires_product_owner": state != "HUMAN_VERIFIED_GOLD",
    }
    validate_artifact("review_state", review)
    return review


def route_failure(
    case_id: str,
    *,
    routed_at: str,
    reason: str = REVIEW_REASON_SCHEMA,
) -> dict[str, Any]:
    review = {
        "schema_version": SCHEMA_VERSION,
        "case_id": case_id,
        "state": "NEEDS_REVIEW",
        "reasons": [reason],
        "routed_at": routed_at,
        "requires_product_owner": True,
    }
    validate_artifact("review_state", review)
    return review


def promote_to_gold(
    review_state: dict[str, Any],
    *,
    promoted_by: str,
    promoted_at: str,
    approval_note: str,
) -> dict[str, Any]:
    validate_artifact("review_state", review_state)
    if review_state["state"] not in {"AI_CURATED_SILVER", "NEEDS_REVIEW"}:
        raise ValueError("only a non-gold benchmark case can be promoted")
    if not promoted_by.strip() or not approval_note.strip():
        raise ValueError("explicit Product Owner identity and approval note are required")
    promoted = {
        "schema_version": SCHEMA_VERSION,
        "case_id": review_state["case_id"],
        "state": "HUMAN_VERIFIED_GOLD",
        "reasons": [],
        "routed_at": review_state["routed_at"],
        "requires_product_owner": False,
        "previous_state": review_state["state"],
        "promoted_by": promoted_by,
        "promoted_at": promoted_at,
        "approval_note": approval_note,
    }
    validate_artifact("review_state", promoted)
    return promoted
