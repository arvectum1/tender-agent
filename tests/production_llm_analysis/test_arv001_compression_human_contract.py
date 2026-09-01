from __future__ import annotations

from scripts.arv001.compress_human_report import _compact_decision
from scripts.arv001.finalize_human_decision_contract import validate_human_decision_contract


def test_compressed_decision_preserves_human_contract_sections() -> None:
    evidence_id = "ARV001-EV-TEST000000000001"
    contract = {
        "decision": {
            "text": "HOLD — проверить срок",
            "evidence_ids": [evidence_id],
        },
        "next_action": {
            "text": "Проверить срок и экономику участия.",
            "evidence_ids": [evidence_id],
        },
        "facts": [
            {
                "label": "Техническое требование",
                "text": "Топливо дизельное, класс не ниже 3.",
                "evidence_ids": [evidence_id],
            }
        ],
        "uncertainty": [],
        "caveats": [
            {
                "text": "Вывод относится к зафиксированному комплекту документов.",
                "evidence_ids": [evidence_id],
            }
        ],
        "evidence_registry": [
            {
                "evidence_id": evidence_id,
                "evidence_type": "source_excerpt",
                "category": "technical",
                "source": "Техническое задание",
                "text": "Топливо дизельное, класс не ниже 3.",
                "locator": None,
            }
        ],
        "fact_count": 1,
        "uncertainty_count": 0,
        "contradiction_count": 0,
    }
    analysis = {
        "technical": {
            "specific_clauses": [
                {
                    "text": "Топливо дизельное, класс не ниже 3.",
                    "source": "Техническое задание",
                    "evidence_ids": [evidence_id],
                }
            ]
        },
        "contract": {},
    }

    rendered = _compact_decision(contract, analysis)
    result = validate_human_decision_contract(rendered, contract)

    assert result["status"] == "PASS"
    assert "<h2>Решение</h2>" in rendered
    assert "<h3>Доказательства</h3>" in rendered
    assert "<h3>Неопределённость</h3>" in rendered
    assert "<h3>Оговорки и ограничения</h3>" in rendered
    assert "<h3>Следующее действие</h3>" in rendered
