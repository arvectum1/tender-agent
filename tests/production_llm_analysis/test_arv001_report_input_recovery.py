from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.arv001.complete_corpus_contract import AcceptanceBlocked
from scripts.arv001.recover_report_rework_input import recover_report_rework_input


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _write_candidate(root: Path, *, report: bytes, canonical: bytes) -> Path:
    controlled = root / "controlled-evidence"
    execution = controlled / "execution-1"
    execution.mkdir(parents=True)
    (controlled / "execution-2").mkdir()
    (execution / "report.html").write_bytes(report)
    (execution / "canonical_report.json").write_bytes(canonical)

    accepted_claims = [
        {"claim_id": f"claim-{index:02d}", "support_status": "supported"}
        for index in range(21)
    ]

    def summary() -> dict[str, object]:
        return {
            "status": "success",
            "canonical_input_eligible": True,
            "accepted_claim_count": 21,
            "accepted_claims": accepted_claims,
            "rejected_claim_count": 0,
            "rejected_claims": [],
            "batch_count": 14,
            "provider_call_count": 14,
            "retry_count": 0,
            "raw_response_stored": False,
            "publication": {
                "canonical_report_file_sha256": _sha(canonical),
            },
        }

    manifest = {
        "manifest_version": "r10.1-controlled-provider-evidence-v3",
        "repeat_count": 2,
        "repeat_identity_verified": True,
        "executions": [summary(), summary()],
    }
    manifest_path = controlled / "controlled-evidence.manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return controlled


def test_recovers_unique_controlled_evidence_by_rejected_report_identity(
    tmp_path: Path,
) -> None:
    report = b"<html>accepted current human report</html>"
    canonical = b'{"canonical":"accepted"}'
    controlled = _write_candidate(tmp_path / "candidate", report=report, canonical=canonical)
    rejected = tmp_path / "upload-ready-report.html"
    rejected.write_bytes(report)

    result = recover_report_rework_input(
        rejected_report=rejected,
        search_roots=[tmp_path],
    )

    assert Path(result["controlled_root"]) == controlled.resolve()
    assert Path(result["canonical_output_path"]) == (
        controlled / "execution-1" / "canonical_report.json"
    ).resolve()
    assert result["rejected_report_sha256"] == _sha(report)
    assert result["canonical_output_sha256"] == _sha(canonical)


def test_rejects_candidate_when_human_report_is_not_byte_identical(
    tmp_path: Path,
) -> None:
    _write_candidate(
        tmp_path / "candidate",
        report=b"<html>different report</html>",
        canonical=b'{"canonical":"accepted"}',
    )
    rejected = tmp_path / "upload-ready-report.html"
    rejected.write_bytes(b"<html>Product Owner rejected this one</html>")

    with pytest.raises(
        AcceptanceBlocked, match="accepted_controlled_evidence_not_found"
    ):
        recover_report_rework_input(
            rejected_report=rejected,
            search_roots=[tmp_path],
        )


def test_rejects_ambiguous_matching_controlled_evidence(tmp_path: Path) -> None:
    report = b"<html>same rejected report</html>"
    canonical = b'{"canonical":"same"}'
    _write_candidate(tmp_path / "first", report=report, canonical=canonical)
    _write_candidate(tmp_path / "second", report=report, canonical=canonical)
    rejected = tmp_path / "upload-ready-report.html"
    rejected.write_bytes(report)

    with pytest.raises(
        AcceptanceBlocked, match="accepted_controlled_evidence_ambiguous"
    ):
        recover_report_rework_input(
            rejected_report=rejected,
            search_roots=[tmp_path],
        )
