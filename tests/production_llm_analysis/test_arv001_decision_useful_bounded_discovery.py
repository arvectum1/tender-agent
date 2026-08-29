from __future__ import annotations

from pathlib import Path

import pytest

from scripts.arv001 import discover_decision_useful_inputs as discovery
from scripts.arv001 import run_decision_useful_candidate_local as runner
from scripts.arv001.complete_corpus_contract import AcceptanceBlocked


def _candidate(root: Path, name: str = "candidate") -> Path:
    value = root / name
    value.mkdir(parents=True)
    for filename in discovery._REQUIRED_CANDIDATE_FILES:
        (value / filename).write_text("{}", encoding="utf-8")
    return value.resolve()


def _noise(root: Path, count: int) -> None:
    for index in range(count):
        (root / f"noise-{index:04d}").mkdir(parents=True)


def test_runtime_root_is_derived_from_accepted_canonical_before_broad_tmp(
    tmp_path: Path,
) -> None:
    runtime = tmp_path / "arv001-final-runtime-test"
    canonical = (
        runtime
        / "acceptance"
        / "controlled-evidence"
        / "execution-1"
        / "canonical_report.json"
    )
    canonical.parent.mkdir(parents=True)
    canonical.write_text("{}", encoding="utf-8")

    roots = runner._default_search_roots(canonical)

    assert roots[0] == runtime.resolve()
    assert Path("/private/tmp").resolve(strict=False) in roots
    assert roots.index(runtime.resolve()) < roots.index(
        Path("/private/tmp").resolve(strict=False)
    )


def test_stream_validates_priority_candidate_before_scope_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = (tmp_path / "private-root").resolve()
    root.mkdir()
    _noise(root, 20)
    candidate = _candidate(root, "arv001-candidate-accepted")

    monkeypatch.setattr(discovery, "_MAX_DISCOVERED_DIRECTORIES", 3)
    monkeypatch.setattr(
        discovery, "_intake_candidates", lambda current, _roots: [current]
    )
    monkeypatch.setattr(discovery, "_pair_is_valid", lambda *_args: True)

    result = discovery.discover_inputs(search_roots=[root])

    assert result["candidate_root"] == str(candidate)
    assert result["intake_root"] == str(candidate)
    assert result["directories_scanned_before_match"] <= 2
    assert result["candidate_manifests_checked"] == 1
    assert result["source_bytes_verified"] is True


def test_invalid_early_candidate_is_not_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = (tmp_path / "root").resolve()
    root.mkdir()
    invalid = _candidate(root, "arv001-candidate-a-invalid")
    valid = _candidate(root, "arv001-candidate-b-valid")

    monkeypatch.setattr(discovery, "_MAX_DISCOVERED_DIRECTORIES", 10)
    monkeypatch.setattr(
        discovery, "_intake_candidates", lambda current, _roots: [current]
    )
    monkeypatch.setattr(
        discovery,
        "_pair_is_valid",
        lambda candidate, _intake, _sha: candidate == valid,
    )

    result = discovery.discover_inputs(search_roots=[root])

    assert invalid != valid
    assert result["candidate_root"] == str(valid)
    assert result["candidate_manifests_checked"] == 2
    assert result["intake_pairs_checked"] == 2


def test_oversized_broad_scope_does_not_block_later_verified_bounded_pair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    broad = (tmp_path / "broad").resolve()
    narrow = (tmp_path / "arv001-runtime").resolve()
    broad.mkdir()
    narrow.mkdir()
    _noise(broad, 8)
    candidate = _candidate(narrow, "arv001-candidate")

    monkeypatch.setattr(discovery, "_MAX_DISCOVERED_DIRECTORIES", 2)
    monkeypatch.setattr(
        discovery, "_intake_candidates", lambda current, _roots: [current]
    )
    monkeypatch.setattr(
        discovery,
        "_pair_is_valid",
        lambda current, _intake, _sha: current == candidate,
    )

    result = discovery.discover_inputs(search_roots=[broad, narrow])

    assert result["candidate_root"] == str(candidate)
    assert result["intake_root"] == str(candidate)
    assert result["selected_discovery_scope"] == str(narrow)
    assert result["oversized_scopes_skipped_before_match"] == 1
    assert result["source_bytes_verified"] is True


def test_scope_too_large_remains_fail_closed_without_verified_pair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    broad = (tmp_path / "broad").resolve()
    broad.mkdir()
    _noise(broad, 8)

    monkeypatch.setattr(discovery, "_MAX_DISCOVERED_DIRECTORIES", 2)

    with pytest.raises(AcceptanceBlocked, match=discovery._SCOPE_TOO_LARGE):
        discovery.discover_inputs(search_roots=[broad])


def test_candidate_collector_compatibility_still_fails_closed_on_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = (tmp_path / "root").resolve()
    root.mkdir()
    _noise(root, 5)
    monkeypatch.setattr(discovery, "_MAX_DISCOVERED_DIRECTORIES", 2)

    with pytest.raises(AcceptanceBlocked, match=discovery._SCOPE_TOO_LARGE):
        discovery._candidate_roots([root])
