from __future__ import annotations

import hashlib
import json

from scripts.arv001 import finalize_human_decision_contract as human


def _canonical() -> dict:
    return {
        "ai_runtime_provenance": {"producer": "production_llm_r10_1"},
        "procurement_number": "0388100001826000047",
        "application_deadline": "2026-07-10T18:30:00+12:00",
        "application_deadline_display": "10.07.2026 18:30 (UTC+12)",
        "analysis_as_of_iso": "2026-07-01T09:00:00+03:00",
        "customer_decision": {
            "recommendation": "Статус срока подачи не определён",
            "reasons": [],
            "confirmed": [],
            "next_action": "Сверить документы.",
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


def _row(text: str, source: str, start: int) -> dict:
    return {
        "text": text,
        "source": source,
        "locator": {"char_start": start, "char_end": start + len(text)},
    }


def _analysis() -> dict:
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
            "payment": [
                _row(
                    "Оплата производится в течение 7 рабочих дней после подписания документа о приемке.",
                    "Проект контракта",
                    100,
                )
            ],
            "security": [
                _row(
                    "Размер обеспечения исполнения Контракта устанавливается в соответствии с частями 6, 6.1, 6.2 статьи 96 ФЗ № 44 от начальной (максимальной) цены Контракта и составляет _______ руб. Обеспечение предоставляется независимой гарантией или внесением денежных средств.",
                    "Проект контракта",
                    400,
                )
            ],
            "acceptance": [
                _row(
                    "Приемка проводится в течение 7 рабочих дней после поставки товара.",
                    "Проект контракта",
                    800,
                )
            ],
            "liability": [
                _row(
                    "Пеня начисляется за каждый день просрочки в размере 1/300 ключевой ставки от не уплаченной в срок суммы.",
                    "Проект контракта",
                    1000,
                )
            ],
            "liability_cap": [],
            "liability_cap_status": "not_found_in_processed_contract_text",
            "termination": [],
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


def test_blank_security_amount_is_explicit_evidence_bound_uncertainty() -> None:
    canonical = _canonical()
    contract = human.build_human_decision_contract(
        canonical_model=canonical,
        canonical_sha=_sha(canonical),
        analysis=_analysis(),
        rendered_html="",
    )

    uncertainty = [
        item
        for item in contract["uncertainty"]
        if item["code"] == "performance_security_amount_unresolved"
    ]
    assert len(uncertainty) == 1
    assert uncertainty[0]["evidence_ids"]
    registry = {item["evidence_id"] for item in contract["evidence_registry"]}
    assert set(uncertainty[0]["evidence_ids"]).issubset(registry)
    assert "не заполнен" in uncertainty[0]["text"]
    assert contract["decision"]["text"].startswith("HOLD")
    assert "подтвердить конкретный размер обеспечения исполнения" in contract["next_action"]["text"]

    rendered = human._replace_decision(
        '<main><section class="decision"><h2>old</h2></section></main>',
        contract,
    )
    validation = human.validate_human_decision_contract(rendered, contract)
    assert validation["status"] == "PASS"
    assert "performance_security_amount_unresolved" not in rendered
    assert "размер обеспечения исполнения не заполнен" in rendered
