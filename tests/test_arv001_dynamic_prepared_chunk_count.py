import json
import os

import pytest

from scripts.arv001.full_pre_provider import _prepare_payload_error
from scripts.arv001.prepared_verification import (
    PreparedVerificationError,
    parse_private_descriptor,
)


HEAD_SHA = "a" * 40
CORPUS_SHA = "b" * 64


def _prepare_payload(chunk_count: object) -> dict[str, object]:
    return {
        "status": "application_prepared",
        "marker": "ARV-001_APPLICATION_PREPARED",
        "head_sha": HEAD_SHA,
        "physical_file_count": 10,
        "logical_document_count": 6,
        "mapped_file_count": 10,
        "extracted_document_count": 10,
        "prepared_chunk_count": chunk_count,
        "post_persistence_gate5_ready": True,
        "controlled_preflight_invocations": 1,
        "controlled_provider_invocations": 0,
        "provider_generation_calls": 0,
        "production_db_mutations": 0,
        "old_arv003_mutations": 0,
        "git_mutations": 0,
    }


def _descriptor(chunk_count: object) -> dict[str, object]:
    return {
        "schema_version": "arv001-prepared-verification-v1",
        "head_sha": HEAD_SHA,
        "target_run_id": "run-1",
        "customer_id": "customer-1",
        "project_id": "project-1",
        "case_id": "case-1",
        "tender_id": "tender-1",
        "run_status": "completed",
        "registry_identity_sha256": "c" * 64,
        "corpus_sha256": CORPUS_SHA,
        "ordered_document_identity_hashes": [f"{index:064x}" for index in range(1, 11)],
        "physical_document_count": 10,
        "logical_document_count": 6,
        "extracted_document_count": 10,
        "chunk_count": chunk_count,
        "snapshot_id": "snapshot-1",
        "snapshot_hash": "d" * 64,
        "source_graph_id": "source-graph-1",
        "source_graph_hash": "e" * 64,
        "gate5_ready": True,
        "controlled_preflight_verified": True,
        "controlled_preflight_invocations": 1,
        "controlled_provider_invocations": 0,
        "provider_generation_calls": 0,
        "provider_results_absent": True,
        "generation_artifacts_absent": True,
    }


@pytest.mark.parametrize("chunk_count", [1, 241, 4096])
def test_prepare_payload_accepts_any_positive_verified_chunk_count(chunk_count: int) -> None:
    assert _prepare_payload_error(_prepare_payload(chunk_count), HEAD_SHA) is None


@pytest.mark.parametrize("chunk_count", [0, -1, True, 1.5, "241"])
def test_prepare_payload_rejects_invalid_chunk_count_types_and_values(chunk_count: object) -> None:
    assert (
        _prepare_payload_error(_prepare_payload(chunk_count), HEAD_SHA)
        == "child_prepared_chunk_count_invalid"
    )


def test_private_descriptor_accepts_nonhistorical_positive_chunk_count(tmp_path) -> None:
    descriptor_path = tmp_path / "prepared-verification.json"
    descriptor_path.write_text(json.dumps(_descriptor(241)), encoding="utf-8")
    os.chmod(descriptor_path, 0o600)

    parsed = parse_private_descriptor(
        descriptor_path,
        expected_head=HEAD_SHA,
        expected_corpus_sha=CORPUS_SHA,
    )

    assert parsed.chunk_count == 241


@pytest.mark.parametrize("chunk_count", [0, -1, True, 1.5, "241"])
def test_private_descriptor_rejects_invalid_chunk_count(tmp_path, chunk_count: object) -> None:
    descriptor_path = tmp_path / "prepared-verification.json"
    descriptor_path.write_text(json.dumps(_descriptor(chunk_count)), encoding="utf-8")
    os.chmod(descriptor_path, 0o600)

    with pytest.raises(PreparedVerificationError) as exc_info:
        parse_private_descriptor(
            descriptor_path,
            expected_head=HEAD_SHA,
            expected_corpus_sha=CORPUS_SHA,
        )

    assert exc_info.value.code == "descriptor_count_invalid"
