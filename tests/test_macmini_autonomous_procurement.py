from datetime import date
from pathlib import Path

import pytest

from scripts.run_macmini_autonomous_procurement import (
    E2EBlocked,
    Selection,
    _recent_publication_window,
    choose_candidate,
    execute,
)


class FakeClient:
    base_url = "http://127.0.0.1:8000"

    def __init__(self, *, run_status: str = "completed_with_warnings", llm: bool = True) -> None:
        self.run_status = run_status
        self.llm = llm
        self.analyze_calls = 0
        self.selected: Selection | None = None

    def search(self, *, query: str, law: str, max_results: int, date_from: str, date_to: str):
        return {
            "outcome": "success_with_results",
            "source": "public_eis_html_44fz",
            "returned_count": 2,
            "eis_pages_fetched": 1,
            "cards": [
                {
                    "reestr_number": "1111111111111111111",
                    "title": "Low candidate",
                    "customer_name": "A",
                    "source": "public_eis_html_44fz",
                    "source_url": "https://zakupki.gov.ru/low",
                    "relevance": {"score": 25, "status": "low", "reasons": ["low"]},
                },
                {
                    "reestr_number": "2222222222222222222",
                    "title": "High candidate",
                    "customer_name": "B",
                    "source": "public_eis_html_44fz",
                    "source_url": "https://zakupki.gov.ru/high",
                    "initial_price": 1_000_000,
                    "relevance": {"score": 75, "status": "high", "reasons": ["match"]},
                },
            ],
        }

    def handoff(self, selection: Selection, *, law: str):
        self.selected = selection
        return {"run_id": "toa-run-test", "status": self.run_status, "warnings": []}

    def analyze(self, run_id: str):
        self.analyze_calls += 1
        self.run_status = "completed_with_warnings"
        return {"run_id": run_id, "status": self.run_status}

    def get_run(self, run_id: str):
        if self.run_status == "docs_required":
            return {
                "run_id": run_id,
                "status": "docs_required",
                "analysis_mode": "not_started",
                "attachments_status": "incomplete_document_set",
                "downloaded_files_count": 1,
                "warnings": ["missing contract"],
                "events": [],
            }
        event_type = "llm_analysis_completed" if self.llm else "stub_analysis_fallback"
        return {
            "run_id": run_id,
            "status": self.run_status,
            "analysis_mode": "llm_tender_operator_provider" if self.llm else "fallback_deterministic_adapter",
            "attachments_status": "downloaded",
            "downloaded_files_count": 4,
            "final_recommendation": {"recommendation": "manual_review_required"},
            "events": [
                {
                    "event_type": event_type,
                    "message": "done",
                    "details": {"resolved_provider": "openai_compatible"} if self.llm else {},
                }
            ],
        }

    def report_html(self, run_id: str):
        return f"<!doctype html><html><body>{run_id}</body></html>"


def test_choose_candidate_uses_highest_relevance():
    cards = [
        {"reestr_number": "1", "relevance": {"score": 40}, "publication_date": "2026-08-01"},
        {"reestr_number": "2", "relevance": {"score": 80}, "publication_date": "2026-07-01"},
    ]

    selected = choose_candidate(cards, min_relevance=20)

    assert selected.registry_number == "2"
    assert selected.relevance_score == 80


def test_choose_candidate_fails_closed_below_threshold():
    with pytest.raises(E2EBlocked) as caught:
        choose_candidate([{"reestr_number": "1", "relevance": {"score": 10}}], min_relevance=20)

    assert caught.value.code == "relevance_below_threshold"


def test_recent_publication_window_is_bounded_to_three_days():
    assert _recent_publication_window(today=date(2026, 9, 1)) == (
        "2026-08-29",
        "2026-09-01",
    )


def test_execute_completes_and_records_llm_provenance(tmp_path: Path):
    client = FakeClient(llm=True)

    result = execute(
        client,
        query="электротехническое оборудование",
        law="44fz",
        max_results=10,
        min_relevance=20,
        output_dir=tmp_path,
    )

    assert result["marker"] == "MACMINI_AUTONOMOUS_PROCUREMENT_E2E_REPORT_READY"
    assert result["selection"]["registry_number"] == "2222222222222222222"
    assert result["selection"]["relevance_score"] == 75
    assert result["llm"]["invoked"] is True
    assert result["llm"]["fallback_used"] is False
    assert result["safety"]["external_actions"] is False
    report_path = Path(result["report"]["saved_path"])
    assert report_path.is_file()
    assert "toa-run-test" in report_path.read_text(encoding="utf-8")


def test_execute_explicitly_reports_deterministic_fallback(tmp_path: Path):
    client = FakeClient(llm=False)

    result = execute(
        client,
        query="кабель",
        law="44fz",
        max_results=10,
        min_relevance=20,
        output_dir=tmp_path,
    )

    assert result["status"] == "report_ready"
    assert result["llm"]["invoked"] is False
    assert result["llm"]["fallback_used"] is True
    assert result["run"]["analysis_mode"] == "fallback_deterministic_adapter"


def test_execute_triggers_analysis_when_handoff_only_prepares_docs(tmp_path: Path):
    client = FakeClient(run_status="ready_to_analyze", llm=True)

    result = execute(
        client,
        query="шкаф управления",
        law="44fz",
        max_results=10,
        min_relevance=20,
        output_dir=tmp_path,
    )

    assert client.analyze_calls == 1
    assert result["run"]["status"] == "completed_with_warnings"


def test_execute_blocks_when_document_set_is_incomplete(tmp_path: Path):
    client = FakeClient(run_status="docs_required")

    with pytest.raises(E2EBlocked) as caught:
        execute(
            client,
            query="кабель",
            law="44fz",
            max_results=10,
            min_relevance=20,
            output_dir=tmp_path,
        )

    assert caught.value.code == "documents_required"
    assert caught.value.details["run_id"] == "toa-run-test"
