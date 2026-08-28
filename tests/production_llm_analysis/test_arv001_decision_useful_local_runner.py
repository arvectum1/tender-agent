from __future__ import annotations

import json
from pathlib import Path

from scripts.arv001 import run_decision_useful_candidate_local as runner


def test_local_runner_discovers_and_delegates_without_external_actions(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    canonical = tmp_path / "canonical.json"
    canonical.write_text("{}", encoding="utf-8")
    candidate = tmp_path / "candidate"
    intake = tmp_path / "intake"
    candidate.mkdir()
    intake.mkdir()
    output = tmp_path / "output"

    monkeypatch.setattr(
        runner,
        "_arguments",
        lambda: type(
            "Args",
            (),
            {
                "output_root": output,
                "canonical_output": canonical,
                "search_roots": [tmp_path],
                "expected_registry_number": "0388100001826000047",
                "expected_corpus_sha": "corpus",
                "expected_canonical_sha": "canonical",
            },
        )(),
    )
    monkeypatch.setattr(
        runner,
        "discover_inputs",
        lambda **_kwargs: {
            "candidate_root": str(candidate),
            "intake_root": str(intake),
        },
    )

    captured: dict = {}

    def fake_build_candidate(**kwargs):
        captured.update(kwargs)
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

    monkeypatch.setattr(runner, "build_candidate", fake_build_candidate)

    assert runner.main() == 0
    assert captured["canonical_output"] == canonical.resolve()
    assert captured["candidate_root"] == candidate
    assert captured["intake_root"] == intake
    assert captured["output_root"] == output

    result = json.loads(capsys.readouterr().out)
    assert result["marker"] == "ARV001_DECISION_USEFUL_LOCAL_CANDIDATE_READY"
    assert result["decision_usefulness_gate"] == "PASS"
    assert result["provider_calls_performed"] is False
    assert result["eis_requests_performed"] is False
    assert result["quality_acceptance_rerun"] is False
    assert result["acknowledgement_touched"] is False
    assert result["product_owner"] == "REJECTED"
    assert result["independent_review"] == "NOT_AUTHORIZED"
    assert result["freeze"] == "NOT_ALLOWED"
