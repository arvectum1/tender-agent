from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from src.modules.benchmark_pipeline import (
    BenchmarkCaseWorkflow,
    BenchmarkContractError,
    aggregate_scorecard,
    canonical_sha256,
    freeze_blind_labels,
    prepare_evaluator_bundle,
    source_bundle_sha256,
    validate_artifact,
    verify_frozen_labels,
    verify_manifest_source_files,
    verify_sut_after_freeze,
)


ACQUIRED = "2026-09-05T11:59:00+00:00"
PREPARED = "2026-09-05T12:00:00+00:00"
EVALUATED = "2026-09-05T12:01:00+00:00"
FROZEN = "2026-09-05T12:02:00+00:00"
PRODUCED = "2026-09-05T12:03:00+00:00"
COMPARED = "2026-09-05T12:04:00+00:00"


def manifest(
    case_id: str = "calibration-1",
    *,
    document_sha: str = "a" * 64,
    source_conflict: bool = False,
    provenance_sufficient: bool = True,
) -> dict:
    documents = [
        {
            "path": "source/notice.html",
            "sha256": document_sha,
            "source_url": "https://example.test/procurement/TEST-001",
        }
    ]
    return {
        "schema_version": "1.1.0",
        "case_id": case_id,
        "procurement": {"notice_number": "TEST-001", "title": "Calibration procurement"},
        "source_urls": ["https://example.test/procurement/TEST-001"],
        "acquired_at": ACQUIRED,
        "documents": documents,
        "source_scope": "public notice and attached procurement documents",
        "source_bundle_sha256": source_bundle_sha256(documents),
        "source_conflict": source_conflict,
        "provenance_sufficient": provenance_sufficient,
    }


def discovery(
    source_hash: str,
    *,
    label: str = "RELEVANT",
    confidence: float = 0.95,
    evaluated_at: str = EVALUATED,
    evidence: list[dict] | None = None,
) -> dict:
    if evidence is None:
        evidence = (
            []
            if label == "UNCLEAR"
            else [{"source_ref": "source/notice.html", "locator": "title"}]
        )
    return {
        "schema_version": "1.1.0",
        "case_id": "calibration-1",
        "source_bundle_sha256": source_hash,
        "label": label,
        "reason": "Independent source-grounded calibration decision.",
        "confidence": confidence,
        "evidence": evidence,
        "evaluator": "independent-evaluator",
        "evaluated_at": evaluated_at,
    }


def truth(
    source_hash: str,
    *,
    case_id: str = "calibration-1",
    confidence: float = 0.95,
    facts: list[dict] | None = None,
    evaluated_at: str = EVALUATED,
) -> dict:
    if facts is None:
        facts = [
            {
                "field": "customer_name",
                "value": "Calibration Customer",
                "evidence": [{"source_ref": "source/notice.html", "locator": "customer"}],
                "confidence": 0.98,
                "abstention": "ASSERTED",
                "materiality": "MATERIAL",
            }
        ]
    return {
        "schema_version": "1.1.0",
        "case_id": case_id,
        "source_bundle_sha256": source_hash,
        "facts": facts,
        "confidence": confidence,
        "evaluator": "independent-evaluator",
        "evaluated_at": evaluated_at,
    }


def normalized_output(
    source_hash: str,
    *,
    case_id: str = "calibration-1",
    label: str = "RELEVANT",
    facts: list[dict] | None = None,
) -> dict:
    if facts is None:
        facts = [
            {
                "field": "customer_name",
                "value": "Calibration Customer",
                "status": "ASSERTED",
                "materiality": "MATERIAL",
            }
        ]
    return {
        "schema_version": "1.1.0",
        "case_id": case_id,
        "source_bundle_sha256": source_hash,
        "discovery": {"label": label, "ranking_delta": 0},
        "facts": facts,
    }


def output_ref(output: dict, freeze: dict, *, produced_at: str = PRODUCED) -> dict:
    return {
        "schema_version": "1.1.0",
        "case_id": output["case_id"],
        "runtime_version": "test-runtime@deadbeef",
        "artifact_refs": {"normalized": "output/normalized.json"},
        "produced_at": produced_at,
        "source_bundle_sha256": output["source_bundle_sha256"],
        "label_set_sha256_at_generation": freeze["label_set_sha256"],
        "normalized_output_sha256": canonical_sha256(output),
    }


def labels_for(manifest_value: dict, *, label: str = "RELEVANT") -> tuple[dict, dict]:
    discovery_value = discovery(manifest_value["source_bundle_sha256"], label=label)
    discovery_value["case_id"] = manifest_value["case_id"]
    truth_value = truth(
        manifest_value["source_bundle_sha256"],
        case_id=manifest_value["case_id"],
    )
    return discovery_value, truth_value


def test_calibration_case_1_matching_high_confidence_routes_silver_then_gold():
    manifest_value = manifest()
    workflow = BenchmarkCaseWorkflow(manifest_value)
    workflow.evaluator_bundle(prepared_at=PREPARED)
    discovery_value, truth_value = labels_for(manifest_value)
    freeze = workflow.freeze_labels(
        discovery_label=discovery_value,
        document_truth=truth_value,
        frozen_at=FROZEN,
    )
    output = normalized_output(manifest_value["source_bundle_sha256"])
    workflow.attach_sut_output(output_ref=output_ref(output, freeze), normalized_output=output)
    result = workflow.compare(compared_at=COMPARED)

    assert result["discovery"]["outcome"] == "MATCH"
    assert result["document"]["tp"] == 1
    assert result["document"]["fp"] == 0
    assert result["document"]["fn"] == 0
    assert workflow.review_state["state"] == "AI_CURATED_SILVER"

    truth_hash_before = canonical_sha256(workflow.document_truth)
    gold = workflow.promote_to_gold(
        reviewer_id="product-owner",
        approval_note="Verified against the frozen source bundle.",
        updated_at="2026-09-05T12:05:00+00:00",
    )
    assert gold["state"] == "HUMAN_VERIFIED_GOLD"
    assert gold["reviewer"] == {"type": "PRODUCT_OWNER", "id": "product-owner"}
    assert canonical_sha256(workflow.document_truth) == truth_hash_before


def test_calibration_case_2_uncertainty_and_unclassified_assertion_route_review():
    manifest_value = manifest(case_id="calibration-2")
    workflow = BenchmarkCaseWorkflow(manifest_value)
    workflow.evaluator_bundle(prepared_at=PREPARED)
    discovery_value = discovery(
        manifest_value["source_bundle_sha256"],
        label="UNCLEAR",
        confidence=0.72,
    )
    discovery_value["case_id"] = "calibration-2"
    truth_value = truth(
        manifest_value["source_bundle_sha256"],
        case_id="calibration-2",
        facts=[
            {
                "field": "delivery_deadline",
                "value": None,
                "evidence": [],
                "confidence": 0.70,
                "abstention": "INSUFFICIENT_EVIDENCE",
                "materiality": "MATERIAL",
            }
        ],
    )
    freeze = workflow.freeze_labels(
        discovery_label=discovery_value,
        document_truth=truth_value,
        frozen_at=FROZEN,
    )
    output = normalized_output(
        manifest_value["source_bundle_sha256"],
        case_id="calibration-2",
        label="RELEVANT",
        facts=[
            {
                "field": "delivery_deadline",
                "value": "2026-10-01",
                "status": "ASSERTED",
                "materiality": "MATERIAL",
            },
            {
                "field": "unexpected_material_fact",
                "value": "claimed",
                "status": "ASSERTED",
                "materiality": "MATERIAL",
            },
        ],
    )
    workflow.attach_sut_output(output_ref=output_ref(output, freeze), normalized_output=output)
    result = workflow.compare(compared_at=COMPARED)

    assert result["discovery"]["outcome"] == "NOT_SCORABLE"
    assert result["document"]["fp"] == 0
    assert set(result["document"]["unsupported_claims"]) == {
        "delivery_deadline",
        "unexpected_material_fact",
    }
    assert result["review_reasons"] == ["UNCLASSIFIED_MATERIAL_DISAGREEMENT"]
    assert workflow.review_state["state"] == "NEEDS_REVIEW"
    assert "LOW_EVALUATOR_CONFIDENCE" in workflow.review_state["reasons"]
    assert "MATERIAL_INSUFFICIENT_EVIDENCE" in workflow.review_state["reasons"]
    assert "UNCLASSIFIED_MATERIAL_DISAGREEMENT" in workflow.review_state["reasons"]


def test_calibration_case_3_mechanical_sut_error_does_not_rewrite_or_poison_truth():
    manifest_value = manifest(case_id="calibration-3")
    workflow = BenchmarkCaseWorkflow(manifest_value)
    workflow.evaluator_bundle(prepared_at=PREPARED)
    discovery_value, truth_value = labels_for(manifest_value)
    discovery_value["case_id"] = "calibration-3"
    truth_value["case_id"] = "calibration-3"
    freeze = workflow.freeze_labels(
        discovery_label=discovery_value,
        document_truth=truth_value,
        frozen_at=FROZEN,
    )
    truth_hash_before = canonical_sha256(workflow.document_truth)
    output = normalized_output(
        manifest_value["source_bundle_sha256"],
        case_id="calibration-3",
        label="IRRELEVANT",
        facts=[
            {
                "field": "customer_name",
                "value": "Wrong Customer",
                "status": "ASSERTED",
                "materiality": "MATERIAL",
            }
        ],
    )
    workflow.attach_sut_output(output_ref=output_ref(output, freeze), normalized_output=output)
    result = workflow.compare(compared_at=COMPARED)

    assert result["discovery"]["outcome"] == "MISMATCH"
    assert result["document"]["fp"] == 1
    assert result["document"]["fn"] == 1
    assert result["material_disagreement"] is True
    assert result["review_reasons"] == []
    assert workflow.review_state["state"] == "AI_CURATED_SILVER"
    assert canonical_sha256(workflow.document_truth) == truth_hash_before


def test_anti_circularity_blocks_pre_freeze_sut_and_detects_tampering():
    manifest_value = manifest()
    workflow = BenchmarkCaseWorkflow(manifest_value)
    output = normalized_output(manifest_value["source_bundle_sha256"])
    with pytest.raises(BenchmarkContractError, match="after independent labels are frozen"):
        workflow.attach_sut_output(output_ref={}, normalized_output=output)

    bundle = workflow.evaluator_bundle(prepared_at=PREPARED)
    discovery_value, truth_value = labels_for(manifest_value)
    freeze = workflow.freeze_labels(
        discovery_label=discovery_value,
        document_truth=truth_value,
        frozen_at=FROZEN,
    )
    with pytest.raises(BenchmarkContractError, match="unavailable after blind labels are frozen"):
        workflow.evaluator_bundle()

    tampered_truth = deepcopy(truth_value)
    tampered_truth["facts"][0]["value"] = "Tampered Customer"
    with pytest.raises(BenchmarkContractError, match="changed after freeze"):
        verify_frozen_labels(freeze, bundle, discovery_value, tampered_truth)

    same_time_ref = output_ref(output, freeze, produced_at=FROZEN)
    with pytest.raises(BenchmarkContractError, match="strictly after blind-label freeze"):
        verify_sut_after_freeze(same_time_ref, output, freeze)

    wrong_label_ref = output_ref(output, freeze)
    wrong_label_ref["label_set_sha256_at_generation"] = "f" * 64
    with pytest.raises(BenchmarkContractError, match="not bound to the frozen blind label set"):
        verify_sut_after_freeze(wrong_label_ref, output, freeze)


def test_evaluator_bundle_rejects_sut_derived_manifest_metadata():
    manifest_value = manifest()
    manifest_value["procurement"]["ranking"] = 1
    with pytest.raises(BenchmarkContractError, match="SUT-derived keys are forbidden"):
        prepare_evaluator_bundle(manifest_value, prepared_at=PREPARED)


def test_schema_is_strict_and_preserves_required_discovery_enum():
    manifest_value = manifest()
    discovery_value = discovery(manifest_value["source_bundle_sha256"])
    discovery_value["label"] = "NOT_RELEVANT"
    with pytest.raises(BenchmarkContractError, match="contract violation"):
        validate_artifact("blind_discovery_label", discovery_value)

    discovery_value = discovery(manifest_value["source_bundle_sha256"])
    discovery_value["tender_agent_answer"] = "leak"
    with pytest.raises(BenchmarkContractError, match="Additional properties"):
        validate_artifact("blind_discovery_label", discovery_value)

    invalid_gold = {
        "schema_version": "1.1.0",
        "case_id": "calibration-1",
        "state": "HUMAN_VERIFIED_GOLD",
        "reasons": [],
        "updated_at": COMPARED,
        "reviewer": {"type": "SYSTEM", "id": "benchmark-pipeline"},
        "previous_state": "AI_CURATED_SILVER",
        "approval_note": "not actually Product Owner verified",
    }
    with pytest.raises(BenchmarkContractError, match="contract violation"):
        validate_artifact("review_state", invalid_gold)


def test_blind_labels_must_follow_prepared_bundle_and_use_known_evidence_refs():
    manifest_value = manifest()
    bundle = prepare_evaluator_bundle(manifest_value, prepared_at=PREPARED)
    discovery_value, truth_value = labels_for(manifest_value)
    discovery_value["evaluated_at"] = "2026-09-05T11:58:00+00:00"
    with pytest.raises(BenchmarkContractError, match="after the blind evaluator bundle"):
        freeze_blind_labels(bundle, discovery_value, truth_value, frozen_at=FROZEN)

    discovery_value, truth_value = labels_for(manifest_value)
    discovery_value["evidence"] = [
        {"source_ref": "source/not-in-bundle.pdf", "locator": "p. 1"}
    ]
    with pytest.raises(BenchmarkContractError, match="outside evaluator bundle"):
        freeze_blind_labels(bundle, discovery_value, truth_value, frozen_at=FROZEN)


def test_manifest_source_hash_verification_detects_file_tampering(tmp_path: Path):
    source_path = tmp_path / "source" / "notice.html"
    source_path.parent.mkdir(parents=True)
    source_path.write_text("original public source", encoding="utf-8")
    document_sha = canonical_sha256("placeholder")
    # File hashes are raw-byte SHA-256, not canonical JSON hashes.
    import hashlib

    document_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()
    manifest_value = manifest(document_sha=document_sha)
    verify_manifest_source_files(manifest_value, tmp_path)

    source_path.write_text("tampered public source", encoding="utf-8")
    with pytest.raises(BenchmarkContractError, match="source hash mismatch"):
        verify_manifest_source_files(manifest_value, tmp_path)


def _completed_case(case_id: str, actual_label: str = "RELEVANT") -> tuple[dict, dict]:
    manifest_value = manifest(case_id=case_id)
    workflow = BenchmarkCaseWorkflow(manifest_value)
    workflow.evaluator_bundle(prepared_at=PREPARED)
    discovery_value, truth_value = labels_for(manifest_value)
    discovery_value["case_id"] = case_id
    truth_value["case_id"] = case_id
    freeze = workflow.freeze_labels(
        discovery_label=discovery_value,
        document_truth=truth_value,
        frozen_at=FROZEN,
    )
    output = normalized_output(
        manifest_value["source_bundle_sha256"],
        case_id=case_id,
        label=actual_label,
    )
    workflow.attach_sut_output(output_ref=output_ref(output, freeze), normalized_output=output)
    result = workflow.compare(compared_at=COMPARED)
    return result, workflow.review_state


def test_scorecard_is_batchable_and_requires_one_review_per_case():
    result_a, review_a = _completed_case("score-a")
    result_b, review_b = _completed_case("score-b", actual_label="IRRELEVANT")
    scorecard = aggregate_scorecard(
        [result_a, result_b],
        [review_a, review_b],
        generated_at="2026-09-05T12:10:00+00:00",
    )
    assert scorecard["case_count"] == 2
    assert scorecard["discovery"]["accuracy"] == 0.5
    assert scorecard["document"]["tp"] == 2
    assert scorecard["review_states"] == {
        "AI_CURATED_SILVER": 2,
        "NEEDS_REVIEW": 0,
        "HUMAN_VERIFIED_GOLD": 0,
    }

    with pytest.raises(BenchmarkContractError, match="exactly one review state"):
        aggregate_scorecard(
            [result_a, result_b],
            [review_a],
            generated_at="2026-09-05T12:10:00+00:00",
        )


def test_gold_promotion_requires_explicit_product_owner_note():
    manifest_value = manifest()
    workflow = BenchmarkCaseWorkflow(manifest_value)
    workflow.evaluator_bundle(prepared_at=PREPARED)
    discovery_value, truth_value = labels_for(manifest_value)
    freeze = workflow.freeze_labels(
        discovery_label=discovery_value,
        document_truth=truth_value,
        frozen_at=FROZEN,
    )
    output = normalized_output(manifest_value["source_bundle_sha256"])
    workflow.attach_sut_output(output_ref=output_ref(output, freeze), normalized_output=output)
    workflow.compare(compared_at=COMPARED)

    with pytest.raises(BenchmarkContractError, match="approval_note"):
        workflow.promote_to_gold(reviewer_id="product-owner", approval_note="")
