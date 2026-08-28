from __future__ import annotations

from pathlib import Path

import pytest

from scripts.arv001.complete_corpus_contract import AcceptanceBlocked
from scripts.arv001 import discover_decision_useful_inputs as discovery


def _candidate(root: Path, name: str = "candidate") -> Path:
    value = root / name
    value.mkdir()
    for filename in discovery._REQUIRED_CANDIDATE_FILES:
        (value / filename).write_text("{}", encoding="utf-8")
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
    assert result["provider_calls_performed"] is False
    assert result["eis_requests_performed"] is False


def test_discovery_fails_closed_when_no_pair_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _candidate(tmp_path)
    monkeypatch.setattr(discovery, "_pair_is_valid", lambda *_args: False)
    with pytest.raises(AcceptanceBlocked, match="frozen_input_pair_not_found"):
        discovery.discover_inputs(search_roots=[tmp_path])


def test_discovery_fails_closed_when_multiple_pairs_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = _candidate(tmp_path)
    intake_a = tmp_path / "intake-a"
    intake_b = tmp_path / "intake-b"
    intake_a.mkdir()
    intake_b.mkdir()
    monkeypatch.setattr(
        discovery,
        "_intake_candidates",
        lambda _candidate, _roots: [intake_a, intake_b],
    )
    monkeypatch.setattr(discovery, "_pair_is_valid", lambda *_args: True)

    with pytest.raises(AcceptanceBlocked, match="frozen_input_pair_ambiguous"):
        discovery.discover_inputs(search_roots=[tmp_path])
