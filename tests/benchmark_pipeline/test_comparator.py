from __future__ import annotations

from benchmarks.pipeline.comparator import aggregate_scorecard, compare_case
from benchmarks.pipeline.contracts import canonical_sha256, source_bundle_sha256
from benchmarks.pipeline.workflow import (
    freeze_labels,
    prepare_evaluator_bundle,
    promote_to_gold,
    route_review,
)


def _artifacts():
    sources = [
        {
            "source_id": "s1",
            "kind": "DOCUMENTATION",
            "title": "Original public documentation",
            "public_url": "https://example.test/procurement/1",
            "retrieved_at": "2026-09-05T12:00:00Z",
            "sha256": "a" * 64,
            "local_path": "sources/doc.pdf",
        }
    ]
    bundle_hash = source_bundle_sha256(sources)
    manifest = {
        "schema_version": "1.0.0",
        "case_id": "calibration-001",
        "procurement_ref": "public-1",
        "created_at": "2026-09-05T12:00:00Z",
        "source_bundle_sha256": bundle_hash,
        "sources": sources,
        "calibration_tags": ["synthetic-contract-test"],
    }
    bundle = prepare_evaluator_bundle(manifest, prepared_at="2026-09-05T12:05:00Z")
    discovery = {
        "schema_version": "1.0.0",
        "case_id": "calibration-001",
        "source_bundle_sha256": bundle_hash,
        "evaluator": "independent-evaluator",
        "evaluated_at": "2026-09-05T12:10:00Z",
        "decision": "RELEVANT",
        "confidence": 0.95,
        "evidence_refs": [{"source_id": "s1", "locator": "page 1"}],
        "material_uncertainties": [],
    }
    truth = {
        "schema_version": "1.0.0",
        "case_id": "calibration-001",
        "source_bundle_sha256": bundle_hash,
        "evaluator": "independent-evaluator",
        "evaluated_at": "2026-09-05T12:10:00Z",
        "facts": [
            {
                "fact_id": "deadline",
                "field_path": "submission.deadline",
                "status": "ASSERTED",
                "materiality": "MATERIAL",
                "confidence": 0.95,
                "value": "2026-09-20T10:00:00+03:00",
                "evidence_refs": [{"source_id": "s1", "locator": "page 2"}],
            },
            {
                "fact_id": "optional-note",
                "field_path": "notes.optional",
                "status": "INSUFFICIENT_EVIDENCE",
                "materiality": "NON_MATERIAL",
                "confidence": 0.90,
                "evidence_refs": [],
            },
        ],
        "material_uncertainties": [],
    }
    freeze = freeze_labels(bundle, discovery, truth, frozen_at="2026-09-05T12:20:00Z")
    sut_output = {
        "schema_version": "1.0.0",
        "case_id": "calibration-001",
        "source_bundle_sha256": bundle_hash,
        "discovery_decision": "RELEVANT",
        "facts": [
            {
                "fact_id": "deadline",
                "field_path": "submission.deadline",
                "status": "ASSERTED",
                "materiality": "MATERIAL",
                "value": "2026-09-20T10:00:00+03:00",
            },
            {
                "fact_id": "optional-note",
                "field_path": "notes.optional",
                "status": "UNKNOWN",
                "materiality": "NON_MATERIAL",
            },
        ],
    }
    sut_ref = {
        "schema_version": "1.0.0",
        "case_id": "calibration-001",
        "produced_at": "2026-09-05T12:25:00Z",
        "source_bundle_sha256": bundle_hash,
        "label_set_sha256_at_generation": freeze["label_set_sha256"],
        "git_revision": "1234567",
        "artifact_path": "local/sut.json",
        "artifact_sha256": "b" * 64,
        "normalized_output_path": "local/normalized.json",
        "normalized_output_sha256": canonical_sha256(sut_output),
    }
    return bundle, discovery, truth, freeze, sut_ref, sut_output


def test_clean_case_is_mechanically_compared_and_silver():
    bundle, discovery, truth, freeze, sut_ref, sut_output = _artifacts()
    comparison = compare_case(
        discovery,
        truth,
        bundle,
        freeze,
        sut_ref,
        sut_output,
        compared_at="2026-09-05T12:30:00Z",
    )
    review = route_review(
        comparison,
        discovery,
        truth,
        routed_at="2026-09-05T12:31:00Z",
    )

    assert comparison["discovery"]["outcome"] == "MATCH"
    assert comparison["document"]["true_positive"] == 1
    assert comparison["document"]["false_positive"] == 0
    assert comparison["document"]["false_negative"] == 0
    assert review["state"] == "AI_CURATED_SILVER"


def test_mechanical_contradiction_scores_error_without_poisoning_label_state():
    bundle, discovery, truth, freeze, sut_ref, sut_output = _artifacts()
    sut_output["facts"][0]["value"] = "2026-09-21T10:00:00+03:00"
    sut_ref["normalized_output_sha256"] = canonical_sha256(sut_output)
    comparison = compare_case(
        discovery,
        truth,
        bundle,
        freeze,
        sut_ref,
        sut_output,
        compared_at="2026-09-05T12:30:00Z",
    )
    review = route_review(
        comparison,
        discovery,
        truth,
        routed_at="2026-09-05T12:31:00Z",
    )

    assert comparison["document"]["false_positive"] == 1
    assert comparison["document"]["false_negative"] == 1
    assert comparison["document"]["items"][0]["outcome"] == "CONTRADICTION"
    assert review["state"] == "AI_CURATED_SILVER"


def test_material_unlabeled_extra_routes_to_review_instead_of_becoming_false_truth():
    bundle, discovery, truth, freeze, sut_ref, sut_output = _artifacts()
    sut_output["facts"].append(
        {
            "fact_id": "new-material-fact",
            "field_path": "contract.new_material_fact",
            "status": "ASSERTED",
            "materiality": "MATERIAL",
            "value": "unexpected",
        }
    )
    sut_ref["normalized_output_sha256"] = canonical_sha256(sut_output)
    comparison = compare_case(
        discovery,
        truth,
        bundle,
        freeze,
        sut_ref,
        sut_output,
        compared_at="2026-09-05T12:30:00Z",
    )
    review = route_review(
        comparison,
        discovery,
        truth,
        routed_at="2026-09-05T12:31:00Z",
    )

    assert comparison["document"]["unscored_extra"] == 1
    assert "UNCLASSIFIED_MATERIAL_DISAGREEMENT" in comparison["review_signals"]
    assert review["state"] == "NEEDS_REVIEW"


def test_material_uncertainty_routes_to_review():
    bundle, discovery, truth, freeze, sut_ref, sut_output = _artifacts()
    truth["facts"][0] = {
        "fact_id": "deadline",
        "field_path": "submission.deadline",
        "status": "INSUFFICIENT_EVIDENCE",
        "materiality": "MATERIAL",
        "confidence": 0.92,
        "evidence_refs": [{"source_id": "s1", "locator": "page 2"}],
    }
    freeze = freeze_labels(bundle, discovery, truth, frozen_at="2026-09-05T12:20:00Z")
    sut_ref["label_set_sha256_at_generation"] = freeze["label_set_sha256"]
    sut_ref["normalized_output_sha256"] = canonical_sha256(sut_output)
    comparison = compare_case(
        discovery,
        truth,
        bundle,
        freeze,
        sut_ref,
        sut_output,
        compared_at="2026-09-05T12:30:00Z",
    )
    review = route_review(
        comparison,
        discovery,
        truth,
        routed_at="2026-09-05T12:31:00Z",
    )
    assert review["state"] == "NEEDS_REVIEW"
    assert "MATERIAL_INSUFFICIENT_EVIDENCE" in review["reasons"]


def test_scorecard_aggregates_review_states_and_metrics():
    bundle, discovery, truth, freeze, sut_ref, sut_output = _artifacts()
    comparison = compare_case(
        discovery,
        truth,
        bundle,
        freeze,
        sut_ref,
        sut_output,
        compared_at="2026-09-05T12:30:00Z",
    )
    silver = route_review(
        comparison,
        discovery,
        truth,
        routed_at="2026-09-05T12:31:00Z",
    )
    gold = promote_to_gold(
        silver,
        promoted_by="product-owner",
        promoted_at="2026-09-05T12:40:00Z",
        approval_note="Verified.",
    )
    scorecard = aggregate_scorecard(
        [comparison],
        [gold],
        generated_at="2026-09-05T12:45:00Z",
    )

    assert scorecard["case_count"] == 1
    assert scorecard["review_states"]["HUMAN_VERIFIED_GOLD"] == 1
    assert scorecard["discovery"]["accuracy"] == 1.0
    assert scorecard["document"]["f1"] == 1.0
