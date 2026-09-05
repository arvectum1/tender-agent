from __future__ import annotations

from collections import Counter
from typing import Any

from .contracts import SCHEMA_VERSION, canonical_json, canonical_sha256, validate_artifact
from .workflow import verify_frozen_labels, verify_sut_after_freeze


def _same_value(left: Any, right: Any) -> bool:
    return canonical_json(left) == canonical_json(right)


def compare_case(
    discovery_label: dict[str, Any],
    document_truth: dict[str, Any],
    evaluator_bundle: dict[str, Any],
    freeze_receipt: dict[str, Any],
    sut_ref: dict[str, Any],
    sut_output: dict[str, Any],
    *,
    compared_at: str,
    comparator_version: str = "1.0.0",
) -> dict[str, Any]:
    validate_artifact("normalized_sut_output", sut_output)
    verify_frozen_labels(freeze_receipt, evaluator_bundle, discovery_label, document_truth)
    verify_sut_after_freeze(sut_ref, freeze_receipt)

    case_id = freeze_receipt["case_id"]
    if sut_output["case_id"] != case_id:
        raise ValueError("normalized SUT output belongs to a different case")
    if sut_output["source_bundle_sha256"] != freeze_receipt["source_bundle_sha256"]:
        raise ValueError("normalized SUT output used a different source bundle")
    if canonical_sha256(sut_output) != sut_ref["normalized_output_sha256"]:
        raise ValueError("normalized SUT output digest does not match tender_agent_output_ref")

    expected_decision = discovery_label["decision"]
    actual_decision = sut_output["discovery_decision"]
    if expected_decision in {"UNKNOWN", "INSUFFICIENT_EVIDENCE"}:
        discovery_outcome = "NOT_SCORABLE"
    else:
        discovery_outcome = "MATCH" if expected_decision == actual_decision else "MISMATCH"

    truth_ids = [fact["fact_id"] for fact in document_truth["facts"]]
    sut_ids = [fact["fact_id"] for fact in sut_output["facts"]]
    if len(truth_ids) != len(set(truth_ids)):
        raise ValueError("blind_document_truth contains duplicate fact_id values")
    if len(sut_ids) != len(set(sut_ids)):
        raise ValueError("normalized SUT output contains duplicate fact_id values")
    truth_by_id = {fact["fact_id"]: fact for fact in document_truth["facts"]}
    sut_by_id = {fact["fact_id"]: fact for fact in sut_output["facts"]}
    counts: Counter[str] = Counter()
    items: list[dict[str, Any]] = []
    review_signals: set[str] = set()

    for fact_id, expected in sorted(truth_by_id.items()):
        actual = sut_by_id.get(fact_id)
        outcome: str
        if expected["status"] == "ASSERTED":
            if actual is None or actual["status"] in {"UNKNOWN", "INSUFFICIENT_EVIDENCE"}:
                outcome = "FALSE_NEGATIVE"
                counts["false_negative"] += 1
            elif actual["status"] == "ASSERTED" and _same_value(expected.get("value"), actual.get("value")):
                outcome = "TRUE_POSITIVE"
                counts["true_positive"] += 1
            elif actual["status"] == "ASSERTED":
                outcome = "CONTRADICTION"
                counts["false_positive"] += 1
                counts["false_negative"] += 1
            else:
                outcome = "FALSE_NEGATIVE"
                counts["false_negative"] += 1
        elif expected["status"] in {"UNKNOWN", "INSUFFICIENT_EVIDENCE", "CONFLICTING_EVIDENCE"}:
            if actual is not None and actual["status"] == "ASSERTED":
                outcome = "UNSUPPORTED_ASSERTION"
                counts["false_positive"] += 1
            else:
                outcome = "ABSTENTION_MATCH"
                counts["abstention_match"] += 1
        else:
            outcome = "UNCLASSIFIED"
            if expected["materiality"] == "MATERIAL":
                review_signals.add("UNCLASSIFIED_MATERIAL_DISAGREEMENT")
        items.append(
            {
                "fact_id": fact_id,
                "materiality": expected["materiality"],
                "expected_status": expected["status"],
                "actual_status": actual["status"] if actual else "MISSING",
                "outcome": outcome,
            }
        )

    for fact_id, actual in sorted(sut_by_id.items()):
        if fact_id in truth_by_id:
            continue
        outcome = "UNLABELED_EXTRA"
        counts["unscored_extra"] += 1
        if actual["materiality"] == "MATERIAL" and actual["status"] == "ASSERTED":
            review_signals.add("UNCLASSIFIED_MATERIAL_DISAGREEMENT")
        items.append(
            {
                "fact_id": fact_id,
                "materiality": actual["materiality"],
                "expected_status": "UNLABELED",
                "actual_status": actual["status"],
                "outcome": outcome,
            }
        )

    tp = counts["true_positive"]
    fp = counts["false_positive"]
    fn = counts["false_negative"]
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and precision + recall
        else None
    )

    result = {
        "schema_version": SCHEMA_VERSION,
        "case_id": case_id,
        "compared_at": compared_at,
        "comparator_version": comparator_version,
        "label_set_sha256": freeze_receipt["label_set_sha256"],
        "sut_artifact_sha256": sut_ref["artifact_sha256"],
        "discovery": {
            "expected": expected_decision,
            "actual": actual_decision,
            "outcome": discovery_outcome,
        },
        "document": {
            "true_positive": tp,
            "false_positive": fp,
            "false_negative": fn,
            "abstention_match": counts["abstention_match"],
            "unscored_extra": counts["unscored_extra"],
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "items": items,
        },
        "schema_failures": [],
        "review_signals": sorted(review_signals),
    }
    validate_artifact("comparison_result", result)
    return result


def aggregate_scorecard(
    comparisons: list[dict[str, Any]],
    reviews: list[dict[str, Any]],
    *,
    generated_at: str,
    comparator_version: str = "1.0.0",
) -> dict[str, Any]:
    for comparison in comparisons:
        validate_artifact("comparison_result", comparison)
    for review in reviews:
        validate_artifact("review_state", review)

    review_by_case = {review["case_id"]: review for review in reviews}
    if set(review_by_case) != {comparison["case_id"] for comparison in comparisons}:
        raise ValueError("scorecard requires exactly one review state per comparison")

    discovery_scored = [
        item for item in comparisons if item["discovery"]["outcome"] != "NOT_SCORABLE"
    ]
    discovery_matches = sum(
        item["discovery"]["outcome"] == "MATCH" for item in discovery_scored
    )
    tp = sum(item["document"]["true_positive"] for item in comparisons)
    fp = sum(item["document"]["false_positive"] for item in comparisons)
    fn = sum(item["document"]["false_negative"] for item in comparisons)
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and precision + recall
        else None
    )
    state_counts = Counter(review["state"] for review in reviews)

    scorecard = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "comparator_version": comparator_version,
        "case_count": len(comparisons),
        "review_states": {
            "AI_CURATED_SILVER": state_counts["AI_CURATED_SILVER"],
            "HUMAN_VERIFIED_GOLD": state_counts["HUMAN_VERIFIED_GOLD"],
            "NEEDS_REVIEW": state_counts["NEEDS_REVIEW"],
        },
        "discovery": {
            "scored": len(discovery_scored),
            "matches": discovery_matches,
            "accuracy": discovery_matches / len(discovery_scored) if discovery_scored else None,
        },
        "document": {
            "true_positive": tp,
            "false_positive": fp,
            "false_negative": fn,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        },
        "needs_review_rate": (
            state_counts["NEEDS_REVIEW"] / len(comparisons) if comparisons else None
        ),
    }
    validate_artifact("scorecard", scorecard)
    return scorecard
