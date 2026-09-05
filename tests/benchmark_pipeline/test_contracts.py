from __future__ import annotations

import pytest

from benchmarks.pipeline.contracts import ContractError, source_bundle_sha256, validate_artifact


def test_case_manifest_forbids_sut_fields():
    sources = [
        {
            "source_id": "s1",
            "kind": "NOTICE",
            "title": "Notice",
            "public_url": "https://example.test/notice",
            "retrieved_at": "2026-09-05T12:00:00Z",
            "sha256": "a" * 64,
            "local_path": "sources/notice.html",
        }
    ]
    manifest = {
        "schema_version": "1.0.0",
        "case_id": "case-1",
        "procurement_ref": "ref-1",
        "created_at": "2026-09-05T12:00:00Z",
        "source_bundle_sha256": source_bundle_sha256(sources),
        "sources": sources,
        "calibration_tags": [],
        "tender_agent_output": {"ranking": 1},
    }
    with pytest.raises(ContractError, match="Additional properties"):
        validate_artifact("case_manifest", manifest)


def test_contract_rejects_invalid_timestamp_and_hash():
    payload = {
        "schema_version": "1.0.0",
        "case_id": "x",
        "prepared_at": "not-a-timestamp",
        "source_bundle_sha256": "bad",
        "sources": [
            {
                "source_id": "s1",
                "kind": "NOTICE",
                "title": "Notice",
                "public_url": "https://example.test",
                "retrieved_at": "also-bad",
                "sha256": "bad",
                "local_path": "sources/a",
            }
        ],
    }
    with pytest.raises(ContractError):
        validate_artifact("evaluator_bundle", payload)
