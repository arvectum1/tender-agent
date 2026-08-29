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


def test_oversized_broad_scope_does_not_block_later_verified_bounded_pair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    broad = (tmp_path / "broad").resolve()
    narrow = (tmp_path / "arv001-runtime").resolve()
    broad.mkdir()
    narrow.mkdir()
    candidate = _candidate(narrow)
    intake = (narrow / "intake").resolve()
    intake.mkdir()

    original_candidate_roots = discovery._candidate_roots

    def fake_candidate_roots(roots: list[Path]) -> list[Path]:
        root = roots[0].resolve(strict=False)
        if root == broad:
            raise AcceptanceBlocked(discovery._SCOPE_TOO_LARGE)
        if root == narrow:
            return [candidate]
        return original_candidate_roots(roots)

    monkeypatch.setattr(discovery, "_candidate_roots", fake_candidate_roots)
    monkeypatch.setattr(
        discovery,
        "_intake_candidates",
        lambda _candidate, _roots: [intake],
    )
    monkeypatch.setattr(discovery, "_pair_is_valid", lambda *_args: True)

    result = discovery.discover_inputs(search_roots=[broad, narrow])

    assert result["candidate_root"] == str(candidate)
    assert result["intake_root"] == str(intake)
    assert result["selected_discovery_scope"] == str(narrow)
    assert result["oversized_scopes_skipped_before_match"] == 1
    assert result["source_bytes_verified"] is True


def test_scope_too_large_remains_fail_closed_when_no_bounded_pair_is_proven(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    broad = (tmp_path / "broad").resolve()
    narrow = (tmp_path / "bounded").resolve()
    broad.mkdir()
    narrow.mkdir()

    def fake_candidate_roots(roots: list[Path]) -> list[Path]:
        if roots[0].resolve(strict=False) == broad:
            raise AcceptanceBlocked(discovery._SCOPE_TOO_LARGE)
        return []

    monkeypatch.setattr(discovery, "_candidate_roots", fake_candidate_roots)

    with pytest.raises(AcceptanceBlocked, match=discovery._SCOPE_TOO_LARGE):
        discovery.discover_inputs(search_roots=[broad, narrow])
