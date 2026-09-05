from __future__ import annotations

from collections import Counter
from typing import Any

from .contract import CONTRACT_VERSION, BenchmarkContractError, canonical_json, validate_artifact
from .workflow import verify_frozen_labels, verify_sut_after_freeze


COMPARATOR_VERSION = "1.1.0"
UNCLASSIFIED_MATERIAL = "UNCLASSIFIED_MATERIAL_DISAGREEMENT"


def _same_value(left: Any, right: Any) -> bool:
    return canonical_json(left) == canonical_json(right)


def compare_case(
    *,
    discovery_label: dict[str, Any],
    document_truth: dict[str, Any],
    evaluator_bundle: dict[str, Any],
    freeze_receipt: dict[str, Any],
    sut_ref: dict[str, Any],
    sut_output: dict[str, Any],
    compared_at: str,
    comparator_version: str = COMPARATOR_VERSION,
) -> dict[str, Any]:
    validate_artifact("normalized_sut_output", sut_output)
    verify_frozen_labels(
        freeze_receipt,
        evaluator_bundle,
        discovery_label,
        document_truth,
    )
    verify_sut_after_freeze(sut_ref, sut_output, freeze_receipt)

    expected_label = discovery_label["label"]
    actual_label = sut_output["discovery"]["label"]
    if expected_label == "UNCLEAR":
        discovery_outcome = "NOT_SCORABLE"
    else:
        discovery_outcome = "MATCH" if expected_label == actual_label else "MISMATCH"

    truth_fields = [fact["field"] for fact in document_truth["facts"]]
    sut_fields = [fact["field"] for fact in sut_output["facts"]]
    if len(truth_fields) != len(set(truth_fields)):
        raise BenchmarkContractError("blind_document_truth contains duplicate fact fields")
    if len(sut_fields) != len(set(sut_fields)):
        raise BenchmarkContractError("normalized SUT output contains duplicate fact fields")

    truth_by_field = {fact["field"]: fact for fact in document_truth["facts"]}
    sut_by_field = {fact["field"]: fact for fact in sut_output["facts"]}
    counts: Counter[str] = Counter()
    items: list[dict[str, Any]] = []
    unsupported: list[str] = []
    contradictions: list[dict[str, Any]] = []
    misses: list[str] = []
    review_reasons: set[str] = set()

    for field, expected in sorted(truth_by_field.items()):
        actual = sut_by_field.get(field)
        expected_status = expected["abstention"]
        materiality = expected["materiality"]

        if expected_status == "ASSERTED":
            if actual is None or actual["status"] in {"UNKNOWN", "INSUFFICIENT_EVIDENCE"}:
                outcome = "FALSE_NEGATIVE"
                counts["fn"] += 1
                misses.append(field)
            elif actual["status"] == "ASSERTED" and _same_value(
                expected.get("value"), actual.get("value")
            ):
                outcome = "TRUE_POSITIVE"
                counts["tp"] += 1
            elif actual["status"] == "ASSERTED":
                outcome = "CONTRADICTION"
                counts["fp"] += 1
                counts["fn"] += 1
                contradictions.append(
                    {
                        "field": field,
                        "expected": expected.get("value"),
                        "actual": actual.get("value"),
                    }
                )
            else:
                outcome = "FALSE_NEGATIVE"
                counts["fn"] += 1
                misses.append(field)
        else:
            if actual is not None and actual["status"] == "ASSERTED":
                outcome = "UNRESOLVED_ASSERTION"
                unsupported.append(field)
                if materiality == "MATERIAL":
                    review_reasons.add(UNCLASSIFIED_MATERIAL)
            else:
                outcome = "ABSTENTION_MATCH"
                counts["abstention_matches"] += 1

        items.append(
            {
                "field": field,
                "materiality": materiality,
                "expected_status": expected_status,
                "actual_status": actual["status"] if actual is not None else "MISSING",
                "outcome": outcome,
            }
        )

    for field, actual in sorted(sut_by_field.items()):
        if field in truth_by_field:
            continue
        counts["unscored_extras"] += 1
        if actual["status"] == "ASSERTED":
            unsupported.append(field)
            if actual["materiality"] == "MATERIAL":
                review_reasons.add(UNCLASSIFIED_MATERIAL)
        items.append(
            {
                "field": field,
                "materiality": actual["materiality"],
                "expected_status": "UNLABELED",
                "actual_status": actual["status"],
                "outcome": "UNLABELED_EXTRA",
            }
        )

    tp = counts["tp"]
    fp = counts["fp"]
    fn = counts["fn"]
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and precision + recall
        else None
    )

    material_disagreement = (
        discovery_outcome == "MISMATCH"
        or bool(contradictions)
        or UNCLASSIFIED_MATERIAL in review_reasons
    )
    result = {
        "schema_version": CONTRACT_VERSION,
        "case_id": freeze_receipt["case_id"],
        "compared_at": compared_at,
        "comparator_version": comparator_version,
        "label_set_sha256": freeze_receipt["label_set_sha256"],
        "discovery": {
            "expected": expected_label,
            "actual": actual_label,
            "outcome": discovery_outcome,
            "ranking_delta": sut_output["discovery"].get("ranking_delta"),
        },
        "document": {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "abstention_matches": counts["abstention_matches"],
            "unscored_extras": counts["unscored_extras"],
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "unsupported_claims": sorted(set(unsupported)),
            "contradictions": contradictions,
            "misses": sorted(set(misses)),
            "items": items,
        },
        "material_disagreement": material_disagreement,
        "review_reasons": sorted(review_reasons),
        "schema_valid": True,
    }
    validate_artifact("comparison_result", result)
    return result


def aggregate_scorecard(
    results: list[dict[str, Any]],
    review_states: list[dict[str, Any]],
    *,
    generated_at: str,
    comparator_version: str = COMPARATOR_VERSION,
) -> dict[str, Any]:
    for result in results:
        validate_artifact("comparison_result", result)
    for review in review_states:
        validate_artifact("review_state", review)

    result_ids = [result["case_id"] for result in results]
    review_ids = [review["case_id"] for review in review_states]
    if len(result_ids) != len(set(result_ids)):
        raise BenchmarkContractError("scorecard comparisons contain duplicate case_id values")
    if len(review_ids) != len(set(review_ids)):
        raise BenchmarkContractError("scorecard reviews contain duplicate case_id values")
    if set(result_ids) != set(review_ids):
        raise BenchmarkContractError("scorecard requires exactly one review state per comparison")

    discovery_scored = [
        result for result in results if result["discovery"]["outcome"] != "NOT_SCORABLE"
    ]
    discovery_matches = sum(
        result["discovery"]["outcome"] == "MATCH" for result in discovery_scored
    )
    tp = sum(result["document"]["tp"] for result in results)
    fp = sum(result["document"]["fp"] for result in results)
    fn = sum(result["document"]["fn"] for result in results)
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and precision + recall
        else None
    )
    states = Counter(review["state"] for review in review_states)

    artifact = {
        "schema_version": CONTRACT_VERSION,
        "generated_at": generated_at,
        "comparator_version": comparator_version,
        "case_count": len(results),
        "review_states": {
            "AI_CURATED_SILVER": states["AI_CURATED_SILVER"],
            "NEEDS_REVIEW": states["NEEDS_REVIEW"],
            "HUMAN_VERIFIED_GOLD": states["HUMAN_VERIFIED_GOLD"],
        },
        "discovery": {
            "scored": len(discovery_scored),
            "matches": discovery_matches,
            "accuracy": discovery_matches / len(discovery_scored) if discovery_scored else None,
        },
        "document": {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        },
        "needs_review_rate": (
            states["NEEDS_REVIEW"] / len(results) if results else None
        ),
    }
    validate_artifact("aggregate_scorecard", artifact)
    return artifact
