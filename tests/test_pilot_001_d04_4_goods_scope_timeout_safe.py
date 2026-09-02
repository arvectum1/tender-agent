from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import run_macmini_autonomous_procurement as base
from scripts import run_macmini_autonomous_goods_procurement as goods_runner


def _card(registry: str, title: str, score: float) -> dict:
    return {
        "reestr_number": registry,
        "title": title,
        "source": "public_eis_html_44fz",
        "source_url": f"https://zakupki.gov.ru/{registry}",
        "publication_date": "2026-09-02",
        "relevance": {"score": score, "status": "high", "reasons": ["match"]},
    }


class GoodsScopeFakeClient:
    base_url = "http://127.0.0.1:8001"

    def __init__(self, cards: list[dict], categories: dict[str, str]) -> None:
        self.cards = cards
        self.categories = categories
        self.selected: list[base.Selection] = []

    def search(self, *, query: str, law: str, max_results: int, date_from: str, date_to: str):
        return {
            "outcome": "success_with_results",
            "source": "public_eis_html_44fz",
            "returned_count": len(self.cards),
            "eis_pages_fetched": 1,
            "cards": self.cards,
        }

    def handoff(self, selection: base.Selection, *, law: str):
        self.selected.append(selection)
        return {"run_id": f"run-{selection.registry_number}", "status": "completed_with_warnings"}

    def get_run(self, run_id: str):
        registry = run_id.removeprefix("run-")
        category = self.categories[registry]
        return {
            "run_id": run_id,
            "status": "completed_with_warnings",
            "analysis_mode": "fallback_deterministic_adapter",
            "attachments_status": "downloaded",
            "downloaded_files_count": 4,
            "final_recommendation": {"recommendation": "manual_review_required"},
            "events": [{"event_type": "stub_analysis_fallback", "message": registry}],
            "runtime_analysis": {
                "schema_version": "tender_operator_runtime_analysis_v1",
                "procurement_category": category,
                "fallback_category": category,
                "grounding_policy": "source_bound_v1",
            },
        }

    def analyze(self, run_id: str):
        raise AssertionError("analysis should not be called in this fixture")

    def report_html(self, run_id: str):
        return f"<!doctype html><html><body>{run_id}</body></html>"


def test_d04_4_prefilter_skips_explicit_services_and_works_before_handoff(tmp_path: Path):
    service = _card(
        "1111111111111111111",
        "Оказание услуг по техническому обслуживанию электрических систем",
        95,
    )
    works = _card(
        "2222222222222222222",
        "Выполнение ремонтных работ автоматических выключателей",
        90,
    )
    goods = _card(
        "3333333333333333333",
        "Поставка автоматических выключателей",
        80,
    )
    client = GoodsScopeFakeClient(
        [service, works, goods],
        {"3333333333333333333": "GOODS"},
    )

    result = goods_runner.execute_goods(
        client,
        query="автоматические выключатели",
        law="44fz",
        max_results=20,
        min_relevance=20,
        output_dir=tmp_path,
    )

    assert [item.registry_number for item in client.selected] == ["3333333333333333333"]
    assert result["selection"]["registry_number"] == "3333333333333333333"
    assert result["selection"]["category_scope_verified"] is True
    assert set(result["selection"]["prefilter_excluded_registry_numbers"]) == {
        "1111111111111111111",
        "2222222222222222222",
    }
    assert result["scope"]["verified_category"] == "GOODS"


def test_d04_4_runtime_category_is_authoritative_and_skips_ambiguous_non_goods(tmp_path: Path):
    ambiguous = _card(
        "4444444444444444444",
        "Комплекс электротехнического оборудования",
        95,
    )
    goods = _card(
        "5555555555555555555",
        "Поставка кабельной продукции",
        80,
    )
    client = GoodsScopeFakeClient(
        [ambiguous, goods],
        {
            "4444444444444444444": "SERVICES",
            "5555555555555555555": "GOODS",
        },
    )

    result = goods_runner.execute_goods(
        client,
        query="электротехническое оборудование",
        law="44fz",
        max_results=20,
        min_relevance=20,
        output_dir=tmp_path,
        max_scope_candidates=3,
    )

    assert [item.registry_number for item in client.selected] == [
        "4444444444444444444",
        "5555555555555555555",
    ]
    assert result["selection"]["registry_number"] == "5555555555555555555"
    assert result["scope"]["runtime_rejections"] == [
        {
            "scope_attempt": 1,
            "registry_number": "4444444444444444444",
            "run_id": "run-4444444444444444444",
            "actual_category": "SERVICES",
            "reason": "runtime_category_mismatch",
        }
    ]
    history = json.loads((tmp_path / "selection-history.json").read_text(encoding="utf-8"))
    assert history["registry_numbers"] == [
        "4444444444444444444",
        "5555555555555555555",
    ]


def test_d04_4_safe_backend_client_converts_raw_timeout_to_blocked(monkeypatch):
    def _timeout(*args, **kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr(base, "urlopen", _timeout)
    client = goods_runner.SafeBackendClient("http://127.0.0.1:8001", timeout_seconds=1)

    with pytest.raises(base.E2EBlocked) as caught:
        client._json("GET", "/api/demo/tender-agent/health")

    assert caught.value.code == "backend_timeout"
    assert caught.value.details["path"] == "/api/demo/tender-agent/health"
    assert caught.value.details["timeout_seconds"] == 1


def test_d04_4_cli_timeout_is_structured_and_never_traceback(monkeypatch, tmp_path: Path, capsys):
    def _timeout(*args, **kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr(base, "urlopen", _timeout)

    exit_code = goods_runner.main(
        [
            "--query",
            "кабельная продукция",
            "--backend-url",
            "http://127.0.0.1:8001",
            "--timeout-seconds",
            "1",
            "--output-dir",
            str(tmp_path),
        ]
    )
    output = capsys.readouterr().out.strip()
    payload = json.loads(output)

    assert exit_code == 20
    assert payload["status"] == "blocked"
    assert payload["code"] == "backend_timeout"
    assert payload["marker"] == "MACMINI_AUTONOMOUS_GOODS_PROCUREMENT_E2E_BLOCKED"
    assert "Traceback" not in output
