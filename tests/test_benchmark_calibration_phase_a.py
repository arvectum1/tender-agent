from __future__ import annotations

import hashlib

import pytest

from scripts.prepare_benchmark_calibration_phase_a import (
    assert_source_only_run,
    build_case_manifest,
    select_exact_card,
    source_only_handoff,
)
from scripts.run_macmini_autonomous_procurement import E2EBlocked
from src.modules.benchmark_pipeline import source_bundle_sha256, validate_artifact


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []

    def _json(self, method: str, path: str, *, payload=None, form=None):
        assert form is None
        self.calls.append((method, path, payload or {}))
        return {"run_id": "run-source-only", "status": "ready_to_analyze"}


def _card(**overrides):
    value = {
        "source": "public_eis_html_44fz",
        "reestr_number": "0848300045426000620",
        "source_url": "https://zakupki.gov.ru/epz/order/notice/ea20/view/common-info.html?regNumber=0848300045426000620",
        "title": "Оказание услуг с использованием ИИ-ассистентов",
        "customer_name": "МКУ Служба кладбищ",
        "initial_price": 100000.0,
        "publication_date": "2026-08-25",
        "deadline": "2026-09-07T09:00:00+03:00",
        "currency": "RUB",
        "status": "Подача заявок",
        "procedure_type": "Электронный запрос котировок",
    }
    value.update(overrides)
    return value


def test_select_exact_card_prefers_latest_exact_revision() -> None:
    older = _card(publication_date="2026-08-20")
    newer = _card(publication_date="2026-08-25")
    other = _card(reestr_number="0000000000000000001", publication_date="2026-09-01")

    selected = select_exact_card(
        [older, other, newer],
        "0848300045426000620",
    )

    assert selected is newer


def test_select_exact_card_fails_closed_when_target_missing() -> None:
    with pytest.raises(E2EBlocked) as exc_info:
        select_exact_card([_card(reestr_number="0000000000000000001")], "0848300045426000620")

    assert exc_info.value.code == "calibration_target_not_found"


def test_source_only_handoff_explicitly_disables_analysis() -> None:
    client = FakeClient()

    response = source_only_handoff(
        client,
        card=_card(),
        registry_number="0848300045426000620",
    )

    assert response["run_id"] == "run-source-only"
    assert len(client.calls) == 1
    method, path, payload = client.calls[0]
    assert method == "POST"
    assert path == "/api/demo/tender-agent/runs/from-search-result"
    assert payload["download_archive"] is True
    assert payload["analyze_after_download"] is False
    assert payload["reestr_number"] == "0848300045426000620"
    assert payload["source_url"].startswith("https://zakupki.gov.ru/")


def test_source_only_handoff_requires_exact_public_url() -> None:
    with pytest.raises(E2EBlocked) as exc_info:
        source_only_handoff(
            FakeClient(),
            card=_card(source_url=None),
            registry_number="0848300045426000620",
        )

    assert exc_info.value.code == "missing_procurement_source_url"


def test_assert_source_only_run_accepts_unanalysed_intake() -> None:
    assert_source_only_run(
        {
            "analysis_mode": "not_started",
            "final_recommendation": None,
            "events": [
                {"event_type": "procurement_handoff_created"},
                {"event_type": "documents_downloaded"},
            ],
        }
    )


@pytest.mark.parametrize(
    ("payload", "expected_code"),
    [
        (
            {"analysis_mode": "deterministic", "final_recommendation": None, "events": []},
            "anti_circularity_analysis_already_started",
        ),
        (
            {"analysis_mode": "not_started", "final_recommendation": {"label": "x"}, "events": []},
            "anti_circularity_sut_output_present",
        ),
        (
            {
                "analysis_mode": "not_started",
                "final_recommendation": None,
                "events": [{"event_type": "analysis_started"}],
            },
            "anti_circularity_analysis_event_present",
        ),
    ],
)
def test_assert_source_only_run_rejects_sut_leakage(payload, expected_code) -> None:
    with pytest.raises(E2EBlocked) as exc_info:
        assert_source_only_run(payload)

    assert exc_info.value.code == expected_code


def test_build_case_manifest_is_contract_valid_and_hash_bound() -> None:
    first = b"public source one"
    second = b"public source two"
    source_documents = [
        {
            "path": "source/notice.html",
            "sha256": hashlib.sha256(first).hexdigest(),
            "source_url": "https://zakupki.gov.ru/notice",
            "provenance_kind": "attachment_url",
        },
        {
            "path": "source/specification.pdf",
            "sha256": hashlib.sha256(second).hexdigest(),
            "source_url": "https://zakupki.gov.ru/specification.pdf",
            "provenance_kind": "attachment_url",
        },
    ]
    procurement = {
        "procurement_notice_number": "0848300045426000620",
        "tender_title": "ИИ-ассистенты",
        "customer_name": "МКУ Служба кладбищ",
        "procurement_law": "44-ФЗ",
        "procurement_source": "public_eis_html_44fz",
        "procurement_url": "https://zakupki.gov.ru/epz/order/notice/view.html?regNumber=0848300045426000620",
    }

    manifest = build_case_manifest(
        case_id="calibration-44fz-0848300045426000620",
        procurement=procurement,
        source_documents=source_documents,
        acquired_at="2026-09-05T18:00:00+00:00",
    )

    validate_artifact("case_manifest", manifest)
    assert manifest["provenance_sufficient"] is True
    assert manifest["source_bundle_sha256"] == source_bundle_sha256(manifest["documents"])
    assert manifest["source_urls"][0] == procurement["procurement_url"]


def test_build_case_manifest_marks_page_fallback_provenance_insufficient() -> None:
    payload = b"public source"
    source_documents = [
        {
            "path": "source/document.pdf",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "source_url": "https://zakupki.gov.ru/epz/order/notice/view.html?regNumber=0848300045426000620",
            "provenance_kind": "procurement_page_fallback",
        }
    ]

    manifest = build_case_manifest(
        case_id="calibration-44fz-0848300045426000620",
        procurement={
            "procurement_notice_number": "0848300045426000620",
            "tender_title": "ИИ-ассистенты",
            "customer_name": "МКУ Служба кладбищ",
            "procurement_law": "44-ФЗ",
            "procurement_source": "public_eis_html_44fz",
            "procurement_url": "https://zakupki.gov.ru/epz/order/notice/view.html?regNumber=0848300045426000620",
        },
        source_documents=source_documents,
        acquired_at="2026-09-05T18:00:00+00:00",
    )

    assert manifest["provenance_sufficient"] is False
