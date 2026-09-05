from __future__ import annotations

from typing import Any

from .contract import CONTRACT_VERSION, validate_artifact


def compare_case(
    *,
    case_id: str,
    discovery_label: dict[str, Any],
    document_truth: dict[str, Any],
    sut_discovery: dict[str, Any],
    sut_facts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Deterministic comparator for calibration and batch execution.

    Discovery is scored as an exact categorical match. Document facts are keyed by
    `field`; abstained evaluator facts do not count as misses. Unsupported SUT claims
    are facts absent from asserted evaluator truth. Contradictions are same-field,
    different-value claims. Missing asserted evaluator fields are false negatives.
    """
    expected_label = discovery_label["label"]
    actual_label = sut_discovery.get("label", "UNCLEAR")
    discovery_match = expected_label == actual_label

    truth_by_field = {
        fact["field"]: fact
        for fact in document_truth["facts"]
        if fact.get("abstention") == "ASSERTED"
    }
    sut_by_field = {fact["field"]: fact for fact in sut_facts if "field" in fact}

    tp = 0
    contradictions: list[dict[str, Any]] = []
    misses: list[str] = []
    unsupported: list[str] = []

    for field, truth in truth_by_field.items():
        if field not in sut_by_field:
            misses.append(field)
            continue
        if sut_by_field[field].get("value") == truth.get("value"):
            tp += 1
        else:
            contradictions.append(
                {
                    "field": field,
                    "expected": truth.get("value"),
                    "actual": sut_by_field[field].get("value"),
                }
            )

    for field in sut_by_field:
        if field not in truth_by_field:
            unsupported.append(field)

    fp = len(unsupported) + len(contradictions)
    fn = len(misses) + len(contradictions)
    material_disagreement = (not discovery_match) or bool(contradictions)

    result = {
        "schema_version": CONTRACT_VERSION,
        "case_id": case_id,
        "discovery": {
            "expected": expected_label,
            "actual": actual_label,
            "match": discovery_match,
            "ranking_delta": sut_discovery.get("ranking_delta"),
        },
        "document": {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "unsupported_claims": unsupported,
            "contradictions": contradictions,
            "misses": misses,
        },
        "material_disagreement": material_disagreement,
        "review_reasons": [],
        "schema_valid": True,
    }
    if not discovery_match:
        result["review_reasons"].append("DISCOVERY_LABEL_MISMATCH")
    if contradictions:
        result["review_reasons"].append("DOCUMENT_CONTRADICTION")
    validate_artifact("comparison_result", result)
    return result


def aggregate_scorecard(results: list[dict[str, Any]], review_states: list[dict[str, Any]]) -> dict[str, Any]:
    tp = sum(result["document"]["tp"] for result in results)
    fp = sum(result["document"]["fp"] for result in results)
    fn = sum(result["document"]["fn"] for result in results)
    discovery_matches = sum(1 for result in results if result["discovery"]["match"])
    states: dict[str, int] = {}
    for review in review_states:
        states[review["state"]] = states.get(review["state"], 0) + 1
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    artifact = {
        "schema_version": CONTRACT_VERSION,
        "case_count": len(results),
        "discovery": {
            "exact_match_rate": discovery_matches / len(results) if results else None,
        },
        "document": {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall},
        "review_states": states,
    }
    validate_artifact("aggregate_scorecard", artifact)
    return artifact
