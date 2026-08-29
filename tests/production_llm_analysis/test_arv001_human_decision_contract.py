from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.arv001.complete_corpus_contract import AcceptanceBlocked
from scripts.arv001 import finalize_human_decision_contract as human


def _canonical(*, with_analysis_time: bool = True) -> dict:
    value = {
        "ai_runtime_provenance": {"producer": "production_llm_r10_1"},
        "procurement_number": "0388100001826000047",
        "application_deadline": "2026-07-10T18:30:00+12:00",
        "application_deadline_display": "10.07.2026 18:30 (UTC+12)",
        "customer_decision": {
            "recommendation": "Статус срока подачи не определён",
            "reasons": ["Основные реквизиты закупки подтверждены."],
            "confirmed": ["позиция и количество"],
            "next_action": "Сверить позиции с ТЗ.",
        },
        "line_items": [],
        "requirements": [],
        "compatibility_sections": {"contract_highlights": []},
        "metadata": {
            "document_set_summary": {
                "status": "complete",
                "logical_document_count": 6,
                "physical_file_count": 10,
                "logical_documents": [],
            }
        },
    }
    if with_analysis_time:
        value["analysis_as_of_iso"] = "2026-08-27T06:50:02+03:00"
    return value


def _row(text: str, source: str, start: int) -> dict:
    return {
        "text": text,
        "source": source,
        "locator": {"char_start": start, "char_end": start + len(text)},
    }


def _analysis(*, contradictory_payment: bool = False) -> dict:
    payment = [
        _row(
            "Оплата производится в течение 7 рабочих дней после подписания документа о приемке.",
            "Проект контракта",
            100,
        )
    ]
    if contradictory_payment:
        payment.extend(
            [
                _row("Аванс не предусмотрен.", "Проект контракта", 220),
                _row("Аванс составляет 30% цены контракта.", "Проект контракта", 260),
            ]
        )
    return {
        "technical": {
            "standards": ["ГОСТ 32511-2013"],
            "specific_clauses": [
                _row(
                    "Топливо должно соответствовать ГОСТ 32511-2013, класс К5.",
                    "Техническое задание",
                    10,
                )
            ],
        },
        "contract": {
            "payment": payment,
            "security": [
                _row(
                    "Обеспечение исполнения контракта составляет 5%; способ — независимая гарантия или внесение денежных средств.",
                    "Обеспечение исполнения контракта",
                    400,
                )
            ],
            "acceptance": [
                _row(
                    "Приемка проводится в течение 7 рабочих дней после поставки товара.",
                    "Проект контракта",
                    600,
                )
            ],
            "liability": [
                _row(
                    "Пеня начисляется за каждый день просрочки в размере 1/300 ключевой ставки от не уплаченной в срок суммы.",
                    "Проект контракта",
                    800,
                )
            ],
            "liability_cap": [],
            "liability_cap_status": "not_found_in_processed_contract_text",
            "termination": [
                _row(
                    "Заказчик вправе принять решение об одностороннем отказе от исполнения контракта.",
                    "Проект контракта",
                    1000,
                )
            ],
        },
        "application_requirements": [
            _row(
                "Заявка должна содержать декларацию о соответствии участника установленным требованиям.",
                "Требования к составу заявки",
                1200,
            )
        ],
    }


def _sha(value: dict) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def test_contract_has_explicit_sections_and_evidence_traceability() -> None:
    canonical = _canonical()
    contract = human.build_human_decision_contract(
        canonical_model=canonical,
        canonical_sha=_sha(canonical),
        analysis=_analysis(),
        rendered_html="<p>Коммерческие предложения не загружены</p>",
    )
    rendered = human._replace_decision(
        '<main><section class="decision"><h2>old</h2></section></main>',
        contract,
    )
    result = human.validate_human_decision_contract(rendered, contract)

    assert result["status"] == "PASS"
    for section in (
        "Решение",
        "Доказательства",
        "Неопределённость",
        "Оговорки и ограничения",
        "Следующее действие",
    ):
        assert section in rendered
    assert 'data-claim-kind="fact"' in rendered
    assert 'data-claim-kind="interpretation"' in rendered
    assert contract["decision"]["evidence_ids"]
    assert contract["next_action"]["evidence_ids"]
    registry = {row["evidence_id"] for row in contract["evidence_registry"]}
    assert all(
        evidence_id in registry
        for fact in contract["facts"]
        for evidence_id in fact["evidence_ids"]
    )


def test_missing_material_evidence_fails_closed() -> None:
    canonical = _canonical()
    empty = {
        "technical": {"standards": [], "specific_clauses": []},
        "contract": {
            "payment": [],
            "security": [],
            "acceptance": [],
            "liability": [],
            "liability_cap": [],
            "liability_cap_status": "not_checked",
            "termination": [],
        },
        "application_requirements": [],
    }
    with pytest.raises(
        AcceptanceBlocked, match="human_decision_material_evidence_missing"
    ):
        human.build_human_decision_contract(
            canonical_model=canonical,
            canonical_sha=_sha(canonical),
            analysis=empty,
            rendered_html="",
        )


def test_material_contradiction_downgrades_to_deterministic_hold() -> None:
    canonical = _canonical()
    contract = human.build_human_decision_contract(
        canonical_model=canonical,
        canonical_sha=_sha(canonical),
        analysis=_analysis(contradictory_payment=True),
        rendered_html="",
    )

    assert contract["contradiction_count"] == 1
    assert contract["decision"]["text"].startswith("HOLD")
    assert any(
        item["code"] == "payment_advance_conflict"
        for item in contract["uncertainty"]
    )
    assert "Сверить противоречащие положения" in contract["next_action"]["text"]


def test_uncertain_deadline_never_produces_confident_go_decision() -> None:
    canonical = _canonical(with_analysis_time=False)
    contract = human.build_human_decision_contract(
        canonical_model=canonical,
        canonical_sha=_sha(canonical),
        analysis=_analysis(),
        rendered_html="",
    )

    assert contract["decision"]["text"].startswith("HOLD")
    assert any(
        item["code"] == "deadline_not_confirmed"
        for item in contract["uncertainty"]
    )
    assert "подтвердить актуальность срока подачи" in contract["next_action"]["text"]


def test_stale_canonical_artifact_fails_closed_before_finalization(
    tmp_path: Path,
) -> None:
    canonical = _canonical()
    canonical_path = tmp_path / "canonical.json"
    canonical_path.write_text(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    root = tmp_path / "candidate"
    root.mkdir()
    (root / "upload-ready-report-decision-useful.html").write_text(
        '<main><section class="decision"><h2>old</h2></section></main>',
        encoding="utf-8",
    )
    (root / "decision-useful-analysis.json").write_text(
        json.dumps(_analysis(), ensure_ascii=False), encoding="utf-8"
    )
    (root / "candidate-manifest.json").write_text(
        json.dumps(
            {
                "registry_number": "0388100001826000047",
                "accepted_canonical_sha256": hashlib.sha256(
                    canonical_path.read_bytes()
                ).hexdigest(),
                "decision_usefulness_gate": {"status": "PASS"},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        AcceptanceBlocked, match="human_decision_stale_canonical_artifact"
    ):
        human.finalize_candidate(
            output_root=root,
            canonical_output=canonical_path,
            expected_canonical_sha="0" * 64,
        )
