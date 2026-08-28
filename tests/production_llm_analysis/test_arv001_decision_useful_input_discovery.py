from __future__ import annotations

from pathlib import Path

import pytest

from scripts.arv001.complete_corpus_contract import AcceptanceBlocked
from scripts.arv001 import discover_decision_useful_inputs as discovery


def _candidate(root: Path, name: str = "candidate", marker: str = "{}") -> Path:
    value = root / name
    value.mkdir()
    for filename in discovery._REQUIRED_CANDIDATE_FILES:
        (value / filename).write_text(marker, encoding="utf-8")
    return value


def test_candidate_scan_is_limited_to_manifest_roots(tmp_path: Path) -> None:
    candidate = _candidate(tmp_path)
    (tmp_path / "noise").mkdir()
    assert discovery._candidate_roots([tmp_path]) == [candidate.resolve()]


def test_discovery_returns_only_unique_proven_pair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = _candidate(tmp_path)
    intake = tmp_path / "intake"
    intake.mkdir()

    monkeypatch.setattr(
        discovery,
        "_intake_candidates",
        lambda _candidate, _roots: [candidate, intake],
    )
    monkeypatch.setattr(
        discovery,
        "_pair_is_valid",
        lambda candidate_value, intake_value, _sha: (
            candidate_value == candidate and intake_value == intake
        ),
    )

    result = discovery.discover_inputs(search_roots=[tmp_path])
    assert result["candidate_root"] == str(candidate.resolve())
    assert result["intake_root"] == str(intake.resolve())
    assert result["physical_document_count"] == 10
    assert result["logical_document_count"] == 6
    assert result["source_bytes_verified"] is True
    assert result["provider_calls_performed"] is False
    assert result["eis_requests_performed"] is False


def test_discovery_fails_closed_when_no_pair_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _candidate(tmp_path)
    monkeypatch.setattr(discovery, "_pair_is_valid", lambda *_args: False)
    with pytest.raises(AcceptanceBlocked, match="frozen_input_pair_not_found"):
        discovery.discover_inputs(search_roots=[tmp_path])


def test_verified_private_copies_choose_narrowest_intake(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = _candidate(tmp_path)
    broad = tmp_path / "intake"
    narrow = broad / "normalized"
    narrow.mkdir(parents=True)
    monkeypatch.setattr(
        discovery,
        "_intake_candidates",
        lambda _candidate, _roots: [broad, narrow],
    )
    monkeypatch.setattr(discovery, "_pair_is_valid", lambda *_args: True)

    result = discovery.discover_inputs(search_roots=[tmp_path])
    assert result["intake_root"] == str(narrow.resolve())
    assert result["verified_pair_count"] == 2


def test_multiple_verified_candidate_copies_are_deterministic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate_a = _candidate(tmp_path, "candidate-a", marker="A")
    candidate_b_parent = tmp_path / "deep"
    candidate_b_parent.mkdir()
    candidate_b = _candidate(candidate_b_parent, "candidate-b", marker="B")
    intake = tmp_path / "intake"
    intake.mkdir()
    monkeypatch.setattr(
        discovery,
        "_intake_candidates",
        lambda _candidate, _roots: [intake],
    )
    monkeypatch.setattr(discovery, "_pair_is_valid", lambda *_args: True)

    result = discovery.discover_inputs(search_roots=[tmp_path])
    # Both pairs are assumed here to have already passed the real accepted-corpus
    # proof. The deeper candidate wins only as a deterministic path tie-breaker.
    assert result["candidate_root"] == str(candidate_b.resolve())
    assert result["verified_pair_count"] == 2
    assert result["candidate_artifact_signature"] == discovery._candidate_signature(
        candidate_b
    )
    assert discovery._candidate_signature(candidate_a) != result[
        "candidate_artifact_signature"
    ]
