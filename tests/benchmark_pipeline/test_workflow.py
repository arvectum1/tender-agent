from __future__ import annotations

from copy import deepcopy

import pytest

from benchmarks.pipeline.contracts import (
    file_sha256,
    source_bundle_sha256,
    validate_case_manifest_consistency,
    verify_manifest_source_files,
)
from benchmarks.pipeline.workflow import (
    AntiCircularityError,
    assert_blind_payload,
    freeze_labels,
    prepare_evaluator_bundle,
    promote_to_gold,
    route_failure,
    verify_frozen_labels,
    verify_sut_after_freeze,
)


def _manifest(source_hash: str) -> dict:
    sources = [
        {
            "source_id": "s1",
            "kind": "DOCUMENTATION",
            "title": "Original public documentation",
            "public_url": "https://example.test/procurement/1",
            "retrieved_at": "2026-09-05T12:00:00Z",
            "sha256": source_hash,
            "local_path": "sources/doc.txt",
        }
    ]
    return {
        "schema_version": "1.0.0",
        "case_id": "calibration-001",
        "procurement_ref": "public-1",
        "created_at": "2026-09-05T12:00:00Z",
        "source_bundle_sha256": source_bundle_sha256(sources),
        "sources": sources,
        "calibration_tags": ["synthetic-contract-test"],
    }


def _labels(bundle_hash: str) -> tuple[dict, dict]:
    discovery = {
        "schema_version": "1.0.0",
        "case_id": "calibration-001",
        "source_bundle_sha256": bundle_hash,
        "evaluator": "independent-evaluator",
        "evaluated_at": "2026-09-05T12:10:00Z",
        "decision": "RELEVANT",
        "confidence": 0.95,
        "rationale_summary": "Source-only determination.",
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
            }
        ],
        "material_uncertainties": [],
    }
    return discovery, truth


def test_source_integrity_and_bundle_digest(tmp_path):
    source_path = tmp_path / "sources" / "doc.txt"
    source_path.parent.mkdir()
    source_path.write_text("original public source", encoding="utf-8")
    manifest = _manifest(file_sha256(source_path))

    validate_case_manifest_consistency(manifest)
    verify_manifest_source_files(manifest, tmp_path)

    source_path.write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="source hash mismatch"):
        verify_manifest_source_files(manifest, tmp_path)


def test_evaluator_bundle_rejects_sut_derived_keys():
    with pytest.raises(AntiCircularityError, match="forbidden"):
        assert_blind_payload(
            {
                "case_id": "x",
                "sources": [],
                "tender_agent_output": {"ranking": 1},
            }
        )


def test_freeze_binds_bundle_and_labels():
    manifest = _manifest("a" * 64)
    bundle = prepare_evaluator_bundle(manifest, prepared_at="2026-09-05T12:05:00Z")
    discovery, truth = _labels(manifest["source_bundle_sha256"])
    receipt = freeze_labels(
        bundle,
        discovery,
        truth,
        frozen_at="2026-09-05T12:20:00Z",
    )

    verify_frozen_labels(receipt, bundle, discovery, truth)

    mutated = deepcopy(truth)
    mutated["facts"][0]["value"] = "changed-after-freeze"
    with pytest.raises(AntiCircularityError, match="changed after freeze"):
        verify_frozen_labels(receipt, bundle, discovery, mutated)


def test_freeze_rejects_evidence_outside_blind_bundle():
    manifest = _manifest("b" * 64)
    bundle = prepare_evaluator_bundle(manifest, prepared_at="2026-09-05T12:05:00Z")
    discovery, truth = _labels(manifest["source_bundle_sha256"])
    truth["facts"][0]["evidence_refs"][0]["source_id"] = "not-in-bundle"

    with pytest.raises(AntiCircularityError, match="outside evaluator bundle"):
        freeze_labels(bundle, discovery, truth, frozen_at="2026-09-05T12:20:00Z")


def test_sut_must_be_strictly_after_freeze():
    manifest = _manifest("c" * 64)
    bundle = prepare_evaluator_bundle(manifest, prepared_at="2026-09-05T12:05:00Z")
    discovery, truth = _labels(manifest["source_bundle_sha256"])
    receipt = freeze_labels(bundle, discovery, truth, frozen_at="2026-09-05T12:20:00Z")
    sut_ref = {
        "schema_version": "1.0.0",
        "case_id": "calibration-001",
        "produced_at": "2026-09-05T12:19:59Z",
        "source_bundle_sha256": manifest["source_bundle_sha256"],
        "label_set_sha256_at_generation": receipt["label_set_sha256"],
        "git_revision": "1234567",
        "artifact_path": "local/sut.json",
        "artifact_sha256": "d" * 64,
        "normalized_output_path": "local/normalized.json",
        "normalized_output_sha256": "e" * 64,
    }
    with pytest.raises(AntiCircularityError, match="strictly after"):
        verify_sut_after_freeze(sut_ref, receipt)


def test_product_owner_promotion_is_explicit():
    silver = {
        "schema_version": "1.0.0",
        "case_id": "calibration-001",
        "state": "AI_CURATED_SILVER",
        "reasons": [],
        "routed_at": "2026-09-05T12:30:00Z",
        "requires_product_owner": True,
    }
    gold = promote_to_gold(
        silver,
        promoted_by="product-owner",
        promoted_at="2026-09-05T12:40:00Z",
        approval_note="Verified against public source bundle.",
    )
    assert gold["state"] == "HUMAN_VERIFIED_GOLD"
    assert gold["previous_state"] == "AI_CURATED_SILVER"
    assert gold["requires_product_owner"] is False

    with pytest.raises(ValueError, match="approval note"):
        promote_to_gold(
            silver,
            promoted_by="product-owner",
            promoted_at="2026-09-05T12:40:00Z",
            approval_note="",
        )


def test_schema_failure_can_fail_closed_to_review():
    review = route_failure(
        "calibration-001",
        routed_at="2026-09-05T12:30:00Z",
    )
    assert review["state"] == "NEEDS_REVIEW"
    assert review["reasons"] == ["SCHEMA_OR_CONSISTENCY_FAILURE"]
