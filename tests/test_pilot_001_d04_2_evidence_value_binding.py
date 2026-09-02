from __future__ import annotations

from types import SimpleNamespace

from src.modules.tender_operator_agent_demo.grounded_fallback_evidence_binding import (
    _bind_fallback_evidence,
)


def test_d04_2_does_not_bind_invented_delivery_number_to_same_theme():
    document = SimpleNamespace(
        file_id="FILE-DELIVERY",
        display_name="Техническое задание.txt",
        text="Срок поставки: 20 календарных дней с даты заключения контракта.",
        evidence_chunks=[],
    )
    outputs = {
        "requirements": {
            "requirements": [
                {
                    "title": "Срок поставки",
                    "detail": "Срок поставки: 15 календарных дней.",
                    "source": "Техническое задание.txt",
                }
            ]
        },
        "trace": {
            "grounding_policy": "source_bound_v1",
            "fallback_category": "GOODS",
        },
    }

    patched = _bind_fallback_evidence(outputs, documents=[document])
    row = patched["requirements"]["requirements"][0]

    assert row["title"] == "INSUFFICIENT_EVIDENCE"
    assert row["evidence_ids"] == []
    assert "15" not in row["detail"]
    assert patched["trace"]["evidence_map"] == {}
