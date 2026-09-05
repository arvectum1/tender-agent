from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.modules.benchmark_pipeline import BenchmarkCaseWorkflow, BenchmarkContractError, compare_case
from src.modules.benchmark_pipeline.comparator import aggregate_scorecard


NOW = "2026-09-05T12:00:00+00:00"


def manifest(case_id: str = "calibration-1", **overrides):
    value = {
        "schema_version": "1.0.0",
        "case_id": case_id,
        "procurement": {"notice_number": "TEST-001", "title": "Calibration procurement"},
        "source_urls": ["https://example.test/procurement/TEST-001"],
        "acquired_at": NOW,
        "documents": [
            {
                "path": "source/notice.html",
                "sha256": "a" * 64,
                "source_url": "https://example.test/procurement/TEST-001",
            }
        ],
        "source_scope": "public notice and attached procurement documents",
        "provenance_sufficient": True,
        "source_conflict": False,
    }
    value.update(overrides)
    return value


def discovery(label="RELEVANT", confidence=0.95):
    return {
        "label": label,
        "reason": "Source materials match the calibration query.",
        "confidence": confidence,
        "evidence": [{"source_ref": "source/notice.html", "locator": "title"}],
    }


def truth(confidence=0.95):
    return {
        "confidence": confidence,
        "facts": [
            {
                "field": "customer_name",
                "value": "Calibration Customer",
                "evidence": [{"source_ref": "source/notice.html", "locator": "customer"}],
                "confidence": 0.98,
                "abstention": "ASSERTED",
            },
            {
                "field": "delivery_deadline",
                "value": None,
                "evidence": [],
                "confidence": 0.60,
                "abstention": "INSUFFICIENT_EVIDENCE",
            },
        ],
    }


def sut_ref(case_id="calibration-1"):
    return {
        "schema_version": "1.0.0",
        "case_id": case_id,
        "runtime_version": "test-runtime@deadbeef",
        "artifact_refs": {"discovery": "output/discovery.json", "document": "output/document.json"},
        "produced_at": NOW,
    }


def test_anti_circularity_blocks_sut_until_labels_are_frozen():
    workflow = BenchmarkCaseWorkflow(manifest())
    with pytest.raises(BenchmarkContractError, match="after independent labels are frozen"):
        workflow.attach_sut_output(sut_ref())

    evaluator_bundle = workflow.evaluator_bundle()
    serialized = json.dumps(evaluator_bundle, sort_keys=True)
    forbidden = ["tender_agent", "ranking_delta", "score_reason", "comparison_result", "artifact_refs"]
    assert all(term not in serialized for term in forbidden)

    frozen_discovery, frozen_truth = workflow.freeze_labels(
        discovery_label=discovery(), document_truth=truth(), frozen_at=NOW
    )
    assert len(frozen_discovery["freeze_hash"]) == 64
    assert len(frozen_truth["freeze_hash"]) == 64

    with pytest.raises(BenchmarkContractError, match="only available before label freeze"):
        workflow.evaluator_bundle()
    with pytest.raises(BenchmarkContractError, match="only be frozen once"):
        workflow.freeze_labels(discovery_label=discovery(), document_truth=truth())


def test_comparator_and_silver_routing_for_matching_case():
    workflow = BenchmarkCaseWorkflow(manifest())
    blind_discovery, blind_truth = workflow.freeze_labels(
        discovery_label=discovery(), document_truth=truth(), frozen_at=NOW
    )
    workflow.attach_sut_output(sut_ref())
    result = compare_case(
        case_id=workflow.case_id,
        discovery_label=blind_discovery,
        document_truth=blind_truth,
        sut_discovery={"label": "RELEVANT", "ranking_delta": 0},
        sut_facts=[{"field": "customer_name", "value": "Calibration Customer"}],
    )
    workflow.record_comparison(result)

    assert result["document"] == {
        "tp": 1,
        "fp": 0,
        "fn": 0,
        "unsupported_claims": [],
        "contradictions": [],
        "misses": [],
    }
    assert workflow.review_state["state"] == "AI_CURATED_SILVER"


def test_material_disagreement_and_low_confidence_route_to_review():
    workflow = BenchmarkCaseWorkflow(manifest(case_id="calibration-2"), confidence_threshold=0.8)
    blind_discovery, blind_truth = workflow.freeze_labels(
        discovery_label=discovery(confidence=0.72), document_truth=truth(), frozen_at=NOW
    )
    workflow.attach_sut_output(sut_ref("calibration-2"))
    result = compare_case(
        case_id=workflow.case_id,
        discovery_label=blind_discovery,
        document_truth=blind_truth,
        sut_discovery={"label": "IRRELEVANT"},
        sut_facts=[{"field": "customer_name", "value": "Wrong Customer"}],
    )
    workflow.record_comparison(result)

    assert result["document"]["tp"] == 0
    assert result["document"]["fp"] == 1
    assert result["document"]["fn"] == 1
    assert result["material_disagreement"] is True
    assert workflow.review_state["state"] == "NEEDS_REVIEW"
    assert "LOW_DISCOVERY_CONFIDENCE" in workflow.review_state["reasons"]
    assert "MATERIAL_DISAGREEMENT" in workflow.review_state["reasons"]


def test_product_owner_can_promote_without_rewriting_truth():
    workflow = BenchmarkCaseWorkflow(manifest(case_id="calibration-3"))
    blind_discovery, blind_truth = workflow.freeze_labels(
        discovery_label=discovery(), document_truth=truth(), frozen_at=NOW
    )
    truth_hash_before = blind_truth["freeze_hash"]
    workflow.attach_sut_output(sut_ref("calibration-3"))
    workflow.record_comparison(
        compare_case(
            case_id=workflow.case_id,
            discovery_label=blind_discovery,
            document_truth=blind_truth,
            sut_discovery={"label": "RELEVANT"},
            sut_facts=[{"field": "customer_name", "value": "Calibration Customer"}],
        )
    )
    review = workflow.promote_to_gold(reviewer_id="product-owner", note="verified against source bundle")

    assert review["state"] == "HUMAN_VERIFIED_GOLD"
    assert review["reviewer"] == {"type": "PRODUCT_OWNER", "id": "product-owner"}
    assert workflow.document_truth["freeze_hash"] == truth_hash_before


def test_aggregate_scorecard_is_batchable():
    results = [
        {
            "schema_version": "1.0.0",
            "case_id": "a",
            "discovery": {"match": True},
            "document": {"tp": 2, "fp": 1, "fn": 0},
            "material_disagreement": False,
            "review_reasons": [],
        },
        {
            "schema_version": "1.0.0",
            "case_id": "b",
            "discovery": {"match": False},
            "document": {"tp": 1, "fp": 0, "fn": 2},
            "material_disagreement": True,
            "review_reasons": ["DISCOVERY_LABEL_MISMATCH"],
        },
    ]
    states = [
        {"state": "AI_CURATED_SILVER"},
        {"state": "NEEDS_REVIEW"},
    ]
    scorecard = aggregate_scorecard(results, states)
    assert scorecard["case_count"] == 2
    assert scorecard["discovery"]["exact_match_rate"] == 0.5
    assert scorecard["document"]["tp"] == 3
    assert scorecard["review_states"] == {"AI_CURATED_SILVER": 1, "NEEDS_REVIEW": 1}


def test_combined_json_schema_is_valid_json():
    schema_path = Path("benchmarks/pipeline/schema/v1/benchmark-artifacts.schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert schema["version"] == "1.0.0"
    assert {
        "caseManifest",
        "blindDiscoveryLabel",
        "blindDocumentTruth",
        "tenderAgentOutputRef",
        "comparisonResult",
        "reviewState",
        "aggregateScorecard",
    } <= set(schema["$defs"])
