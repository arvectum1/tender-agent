from __future__ import annotations

from types import SimpleNamespace

from src.modules.tender_operator_agent_demo.grounded_fallback_evidence_binding import (
    _bind_fallback_evidence,
)


def _document(
    text: str,
    *,
    file_id: str = "FILE-GOODS-1",
    name: str = "Техническое задание.txt",
    evidence_chunks: list[dict] | None = None,
):
    return SimpleNamespace(
        file_id=file_id,
        display_name=name,
        text=text,
        evidence_chunks=evidence_chunks or [],
    )


def _goods_outputs(row: dict) -> dict:
    return {
        "requirements": {"requirements": [row]},
        "trace": {
            "grounding_policy": "source_bound_v1",
            "fallback_category": "GOODS",
        },
    }


def test_d04_2_goods_requirement_gets_stable_document_evidence_ref():
    documents = [
        _document(
            "Поставка автоматических выключателей. Количество товара: 10 штук."
        )
    ]
    outputs = _goods_outputs(
        {
            "title": "Количество товара",
            "detail": "Количество товара: 10 штук.",
            "source": "Техническое задание.txt",
            "type": "техническое требование",
        }
    )

    patched = _bind_fallback_evidence(outputs, documents=documents)
    row = patched["requirements"]["requirements"][0]
    trace = patched["trace"]

    assert row["evidence_ids"] == ["FILE-GOODS-1::document"]
    assert row["source_document"] == "Техническое задание.txt"
    assert row["evidence_state"] == "bound"
    assert trace["fallback_evidence_binding_policy"] == "goods_claim_evidence_binding_v1"
    assert trace["fallback_evidence_binding_count"] == 1
    assert trace["fallback_evidence_binding_complete"] is True
    assert trace["evidence_map"]["FILE-GOODS-1::document"]["file_id"] == "FILE-GOODS-1"
    assert trace["evidence_map"]["FILE-GOODS-1::document"]["locator"] == "document"


def test_d04_2_prefers_existing_chunk_evidence_id_and_locator():
    documents = [
        _document(
            "Поставка кабеля. Срок поставки: 20 календарных дней.",
            evidence_chunks=[
                {
                    "evidence_id": "EV-DELIVERY-20D",
                    "text": "Срок поставки: 20 календарных дней с даты заключения контракта.",
                    "page": 7,
                }
            ],
        )
    ]
    outputs = _goods_outputs(
        {
            "title": "Срок поставки",
            "detail": "Срок поставки: 20 календарных дней.",
            "source": "Техническое задание.txt",
        }
    )

    patched = _bind_fallback_evidence(outputs, documents=documents)
    row = patched["requirements"]["requirements"][0]

    assert row["evidence_ids"] == ["EV-DELIVERY-20D"]
    assert patched["trace"]["evidence_map"]["EV-DELIVERY-20D"]["locator"] == "page:7"


def test_d04_2_unresolvable_goods_requirement_fails_closed():
    documents = [_document("Поставка автоматических выключателей. Количество 10 штук.")]
    outputs = _goods_outputs(
        {
            "title": "Сертификат происхождения",
            "detail": "Нужно предоставить сертификат происхождения из Италии.",
            "source": "Документы закупки",
        }
    )

    patched = _bind_fallback_evidence(outputs, documents=documents)
    row = patched["requirements"]["requirements"][0]

    assert row["title"] == "INSUFFICIENT_EVIDENCE"
    assert row["evidence_ids"] == []
    assert row["evidence_state"] == "insufficient"
    assert patched["trace"]["fallback_evidence_binding_count"] == 0
    assert patched["trace"]["fallback_evidence_binding_complete"] is True


def test_d04_2_does_not_modify_non_goods_fallback():
    outputs = {
        "requirements": {
            "requirements": [
                {
                    "title": "Срок оказания услуг",
                    "detail": "Услуги оказываются в течение 20 дней.",
                }
            ]
        },
        "trace": {
            "grounding_policy": "source_bound_v1",
            "fallback_category": "SERVICES",
        },
    }

    patched = _bind_fallback_evidence(
        outputs,
        documents=[_document("Услуги оказываются в течение 20 дней.")],
    )

    assert patched == outputs
    assert "fallback_evidence_binding_policy" not in patched["trace"]
