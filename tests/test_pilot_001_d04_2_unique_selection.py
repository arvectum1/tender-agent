from __future__ import annotations

from pathlib import Path

import pytest

from scripts.run_macmini_autonomous_procurement import (
    E2EBlocked,
    Selection,
    choose_candidate,
    execute,
)


def _cards() -> list[dict]:
    return [
        {
            "reestr_number": "1111111111111111111",
            "title": "Second candidate",
            "source": "public_eis_html_44fz",
            "source_url": "https://zakupki.gov.ru/second",
            "publication_date": "2026-09-02",
            "relevance": {"score": 60, "status": "high", "reasons": ["match"]},
        },
        {
            "reestr_number": "2222222222222222222",
            "title": "Best candidate",
            "source": "public_eis_html_44fz",
            "source_url": "https://zakupki.gov.ru/best",
            "publication_date": "2026-09-02",
            "relevance": {"score": 80, "status": "high", "reasons": ["match"]},
        },
    ]


def test_d04_2_choose_candidate_excludes_already_used_registry_number():
    selected = choose_candidate(
        _cards(),
        min_relevance=20,
        excluded_registry_numbers=["2222222222222222222"],
    )

    assert selected.registry_number == "1111111111111111111"
    assert selected.relevance_score == 60


def test_d04_2_choose_candidate_deduplicates_same_procurement_before_ranking():
    cards = _cards() + [
        {
            "reestr_number": "2222222222222222222",
            "title": "Duplicate stale card",
            "publication_date": "2026-09-01",
            "relevance": {"score": 30},
        }
    ]

    selected = choose_candidate(cards, min_relevance=20)

    assert selected.registry_number == "2222222222222222222"
    assert selected.card["title"] == "Best candidate"
    assert selected.relevance_score == 80


def test_d04_2_choose_candidate_fails_closed_when_only_excluded_cards_remain():
    with pytest.raises(E2EBlocked) as caught:
        choose_candidate(
            _cards(),
            min_relevance=20,
            excluded_registry_numbers=[
                "1111111111111111111",
                "2222222222222222222",
            ],
        )

    assert caught.value.code == "no_unique_search_cards"
    assert set(caught.value.details["discovered_registry_numbers"]) == {
        "1111111111111111111",
        "2222222222222222222",
    }


class UniqueFakeClient:
    base_url = "http://127.0.0.1:8000"

    def __init__(self, *, first_docs_required: bool = False) -> None:
        self.first_docs_required = first_docs_required
        self.selected: list[Selection] = []

    def search(self, *, query: str, law: str, max_results: int, date_from: str, date_to: str):
        return {
            "outcome": "success_with_results",
            "source": "public_eis_html_44fz",
            "returned_count": 2,
            "eis_pages_fetched": 1,
            "cards": _cards(),
        }

    def handoff(self, selection: Selection, *, law: str):
        self.selected.append(selection)
        return {"run_id": f"run-{selection.registry_number}", "status": "completed_with_warnings"}

    def get_run(self, run_id: str):
        selected_registry = run_id.removeprefix("run-")
        if self.first_docs_required and len(self.selected) == 1:
            return {
                "run_id": run_id,
                "status": "docs_required",
                "analysis_mode": "not_started",
                "attachments_status": "incomplete_document_set",
                "downloaded_files_count": 1,
                "warnings": ["missing contract"],
                "events": [],
            }
        return {
            "run_id": run_id,
            "status": "completed_with_warnings",
            "analysis_mode": "fallback_deterministic_adapter",
            "attachments_status": "downloaded",
            "downloaded_files_count": 4,
            "final_recommendation": {"recommendation": "manual_review_required"},
            "events": [{"event_type": "stub_analysis_fallback", "message": selected_registry}],
        }

    def analyze(self, run_id: str):
        raise AssertionError("analysis should not be called in this fixture")

    def report_html(self, run_id: str):
        return f"<!doctype html><html><body>{run_id}</body></html>"


def test_d04_2_execute_automatically_selects_a_new_procurement_on_next_run(tmp_path: Path):
    client = UniqueFakeClient()

    first = execute(
        client,
        query="электротехническое оборудование",
        law="44fz",
        max_results=10,
        min_relevance=20,
        output_dir=tmp_path,
    )
    second = execute(
        client,
        query="электротехническое оборудование",
        law="44fz",
        max_results=10,
        min_relevance=20,
        output_dir=tmp_path,
    )

    assert first["selection"]["registry_number"] == "2222222222222222222"
    assert second["selection"]["registry_number"] == "1111111111111111111"
    assert second["selection"]["method"] == "deterministic_highest_relevance_unique"
    assert second["selection"]["excluded_registry_numbers"] == ["2222222222222222222"]
    assert Path(second["selection"]["selection_history_path"]).is_file()


def test_d04_2_blocked_procurement_is_reserved_so_next_run_does_not_repeat_it(tmp_path: Path):
    client = UniqueFakeClient(first_docs_required=True)

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
    assert caught.value.details["registry_number"] == "2222222222222222222"

    client.first_docs_required = False
    second = execute(
        client,
        query="кабель",
        law="44fz",
        max_results=10,
        min_relevance=20,
        output_dir=tmp_path,
    )

    assert second["selection"]["registry_number"] == "1111111111111111111"
