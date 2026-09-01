from __future__ import annotations

import json
import re
from pathlib import Path

from scripts.arv001 import run_decision_useful_candidate_local as runner
from scripts.arv001.complete_corpus_contract import AcceptanceBlocked


def _args(output: Path, canonical: Path, search_root: Path):
    return type(
        "Args",
        (),
        {
            "output_root": output,
            "canonical_output": canonical,
            "search_roots": [search_root],
            "expected_registry_number": "0388100001826000047",
            "expected_corpus_sha": "corpus",
            "expected_canonical_sha": "canonical",
        },
    )()


def _build_result() -> dict:
    return {
        "status": "decision_useful_candidate_for_product_owner_review",
        "report_sha256": "report",
        "material_detail_count": 12,
        "decision_usefulness_gate": {
            "status": "PASS",
            "checks": {"payment_clause_count": 1},
        },
        "accepted_canonical_sha256": "canonical",
        "frozen_corpus_sha256": "corpus",
        "physical_document_count": 10,
        "logical_document_count": 6,
    }


def _human_result() -> dict:
    return {
        "status": "PASS",
        "report_sha256": "human-report",
        "analysis_sha256": "human-analysis",
        "human_decision_contract_sha256": "human-contract",
        "validation": {
            "status": "PASS",
            "evidence_count": 8,
            "fact_count": 7,
            "uncertainty_count": 1,
            "contradiction_count": 0,
        },
        "decision": "HOLD — сначала завершить проверку",
        "next_action": "Проверить существенные условия.",
        "evidence_count": 8,
        "fact_count": 7,
        "uncertainty_count": 1,
        "contradiction_count": 0,
    }


def test_local_runner_discovers_delegates_and_validates_without_external_actions(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    canonical = tmp_path / "canonical.json"
    canonical.write_text("{}", encoding="utf-8")
    candidate = tmp_path / "candidate"
    intake = tmp_path / "intake"
    candidate.mkdir()
    intake.mkdir()
    output = tmp_path / "output"

    monkeypatch.setattr(runner, "_arguments", lambda: _args(output, canonical, tmp_path))
    monkeypatch.setattr(
        runner,
        "discover_inputs",
        lambda **_kwargs: {
            "candidate_root": str(candidate),
            "intake_root": str(intake),
            "source_bytes_verified": True,
            "verified_pair_count": 2,
        },
    )

    captured: dict = {}

    def fake_build_candidate(**kwargs):
        captured.update(kwargs)
        output.mkdir()
        return _build_result()

    monkeypatch.setattr(runner, "build_candidate", fake_build_candidate)
    monkeypatch.setattr(runner, "finalize_candidate", lambda **_kwargs: _human_result())
    monkeypatch.setattr(
        runner,
        "_validate_published_candidate",
        lambda _root: {
            "status": "PASS",
            "exact_standard_count": 1,
            "contract_visible_counts": {"payment": 1},
            "human_decision_contract_present": True,
            "human_decision_evidence_count": 8,
            "human_decision_fact_count": 7,
            "human_decision_uncertainty_count": 1,
            "human_decision_contradiction_count": 0,
        },
    )

    assert runner.main() == 0
    assert captured["canonical_output"] == canonical.resolve()
    assert captured["candidate_root"] == candidate
    assert captured["intake_root"] == intake
    assert captured["output_root"] == output

    result = json.loads(capsys.readouterr().out)
    assert result["marker"] == "ARV001_HUMAN_DECISION_LOCAL_CANDIDATE_READY"
    assert result["report_sha256"] == "human-report"
    assert result["human_decision_contract_sha256"] == "human-contract"
    assert result["decision_usefulness_gate"] == "PASS"
    assert result["human_decision_contract"]["status"] == "PASS"
    assert result["rendered_material_validation"]["status"] == "PASS"
    assert result["source_bytes_verified"] is True
    assert result["verified_private_input_pairs"] == 2
    assert result["provider_calls_performed"] is False
    assert result["eis_requests_performed"] is False
    assert result["quality_acceptance_rerun"] is False
    assert result["acknowledgement_touched"] is False
    assert result["product_owner"] == "REJECTED"
    assert result["independent_review"] == "NOT_AUTHORIZED"
    assert result["freeze"] == "NOT_ALLOWED"


def test_local_runner_removes_just_created_candidate_when_render_validation_fails(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    canonical = tmp_path / "canonical.json"
    canonical.write_text("{}", encoding="utf-8")
    candidate = tmp_path / "candidate"
    intake = tmp_path / "intake"
    candidate.mkdir()
    intake.mkdir()
    output = tmp_path / "output"

    monkeypatch.setattr(runner, "_arguments", lambda: _args(output, canonical, tmp_path))
    monkeypatch.setattr(
        runner,
        "discover_inputs",
        lambda **_kwargs: {
            "candidate_root": str(candidate),
            "intake_root": str(intake),
        },
    )

    def fake_build_candidate(**_kwargs):
        output.mkdir()
        (output / "partial.txt").write_text("not a candidate", encoding="utf-8")
        return _build_result()

    monkeypatch.setattr(runner, "build_candidate", fake_build_candidate)
    monkeypatch.setattr(runner, "finalize_candidate", lambda **_kwargs: _human_result())
    monkeypatch.setattr(
        runner,
        "_validate_published_candidate",
        lambda _root: (_ for _ in ()).throw(
            AcceptanceBlocked("decision_useful_rendered_payment_missing")
        ),
    )

    assert runner.main() == 2
    assert not output.exists()
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "FAIL_CLOSED"
    assert result["failure_code"] == "decision_useful_rendered_payment_missing"
    assert result["product_owner"] == "REJECTED"


def test_local_runner_removes_candidate_when_human_contract_finalization_fails(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    canonical = tmp_path / "canonical.json"
    canonical.write_text("{}", encoding="utf-8")
    candidate = tmp_path / "candidate"
    intake = tmp_path / "intake"
    candidate.mkdir()
    intake.mkdir()
    output = tmp_path / "output"

    monkeypatch.setattr(runner, "_arguments", lambda: _args(output, canonical, tmp_path))
    monkeypatch.setattr(
        runner,
        "discover_inputs",
        lambda **_kwargs: {
            "candidate_root": str(candidate),
            "intake_root": str(intake),
        },
    )

    def fake_build_candidate(**_kwargs):
        output.mkdir()
        return _build_result()

    monkeypatch.setattr(runner, "build_candidate", fake_build_candidate)
    monkeypatch.setattr(
        runner,
        "finalize_candidate",
        lambda **_kwargs: (_ for _ in ()).throw(
            AcceptanceBlocked("human_decision_fact_without_evidence")
        ),
    )

    assert runner.main() == 2
    assert not output.exists()
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "FAIL_CLOSED"
    assert result["failure_code"] == "human_decision_fact_without_evidence"
    assert result["product_owner"] == "REJECTED"


def test_local_runner_fail_closed_on_regex_render_error(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    canonical = tmp_path / "canonical.json"
    canonical.write_text("{}", encoding="utf-8")
    candidate = tmp_path / "candidate"
    intake = tmp_path / "intake"
    candidate.mkdir()
    intake.mkdir()
    output = tmp_path / "output"

    monkeypatch.setattr(runner, "_arguments", lambda: _args(output, canonical, tmp_path))
    monkeypatch.setattr(
        runner,
        "discover_inputs",
        lambda **_kwargs: {
            "candidate_root": str(candidate),
            "intake_root": str(intake),
        },
    )

    def fake_build_candidate(**_kwargs):
        output.mkdir()
        return _build_result()

    monkeypatch.setattr(runner, "build_candidate", fake_build_candidate)
    monkeypatch.setattr(
        runner,
        "finalize_candidate",
        lambda **_kwargs: (_ for _ in ()).throw(re.error("bad escape \\l")),
    )

    assert runner.main() == 2
    assert not output.exists()
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "FAIL_CLOSED"
    assert result["failure_code"] == "human_decision_regex_render_failed"
    assert result["provider_calls_performed"] is False
    assert result["eis_requests_performed"] is False
    assert result["quality_acceptance_rerun"] is False
    assert result["acknowledgement_touched"] is False
    assert result["product_owner"] == "REJECTED"
    assert result["independent_review"] == "NOT_AUTHORIZED"
    assert result["freeze"] == "NOT_ALLOWED"
