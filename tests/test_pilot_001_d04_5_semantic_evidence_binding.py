from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.modules.tender_operator_agent_demo.grounded_fallback_evidence_binding import (
    _bind_fallback_evidence,
)


def _doc(text: str, *, chunks: list[dict] | None = None):
    return SimpleNamespace(
        file_id="FILE-01",
        display_name="Техническое задание.txt",
        text=text,
        evidence_chunks=chunks or [],
    )


def _outputs(*rows: dict) -> dict:
    return {
        "requirements": {"requirements": list(rows)},
        "trace": {"grounding_policy": "source_bound_v1", "fallback_category": "GOODS"},
    }


def _row(title: str, detail: str) -> dict:
    return {"title": title, "detail": detail, "source": "Техническое задание.txt"}


def _result(claim: str, evidence: str) -> dict:
    patched = _bind_fallback_evidence(
        _outputs(_row("Требование", claim)), documents=[_doc(evidence)]
    )
    return patched["requirements"]["requirements"][0]


def test_exact_gost_positive():
    assert _result("Соответствие ГОСТ 31565-2012", "Изделие соответствует ГОСТ 31565-2012.")["evidence_state"] == "bound"


def test_generic_gost_is_not_concrete_evidence():
    assert _result("Соответствие ГОСТ 31565-2012", "Продукция соответствует требованиям действующих ГОСТ и ТУ.")["title"] == "INSUFFICIENT_EVIDENCE"


def test_wrong_standard_fails_closed():
    assert _result("ГОСТ 31565-2012", "Изделие соответствует ГОСТ 31996-2012.")["evidence_state"] == "insufficient"


def test_numeric_exact_positive():
    assert _result("Срок поставки — 15 календарных дней", "Срок поставки составляет 15 календарных дней.")["evidence_state"] == "bound"


def test_numeric_mismatch_fails_closed():
    assert _result("Срок поставки — 15 календарных дней", "Срок поставки составляет 20 календарных дней.")["title"] == "INSUFFICIENT_EVIDENCE"


def test_same_number_with_wrong_context_fails_closed():
    assert _result("Срок поставки — 15 дней", "Количество товара — 15 шт.")["title"] == "INSUFFICIENT_EVIDENCE"


def test_safety_positive():
    assert _result("Требования пожарной безопасности", "Соблюдаются требования пожарной безопасности.")["evidence_state"] == "bound"


def test_generic_compliance_does_not_bind_safety():
    assert _result("Требования пожарной безопасности", "Товар соответствует установленным требованиям качества.")["title"] == "INSUFFICIENT_EVIDENCE"


def test_generic_delivery_does_not_bind_concrete_deadline():
    assert _result("Поставка в течение 10 рабочих дней", "Предмет закупки: поставка электротехнической продукции.")["title"] == "INSUFFICIENT_EVIDENCE"


def test_whole_document_generic_vocabulary_does_not_bind():
    text = "Товар, продукция, оборудование, требования и качество. " * 20
    assert _result("Степень защиты не ниже IP54", text)["title"] == "INSUFFICIENT_EVIDENCE"


def test_excerpt_validation_keeps_concrete_anchor():
    text = "Общие требования к продукции. " * 30 + "Соответствие ГОСТ 31565-2012 обязательно."
    patched = _bind_fallback_evidence(
        _outputs(_row("Стандарт", "Соответствие ГОСТ 31565-2012")), documents=[_doc(text)]
    )
    evidence = patched["trace"]["evidence_map"]["FILE-01::document"]
    assert "31565-2012" in evidence["excerpt"]


@pytest.mark.parametrize(
    ("evidence", "expected"),
    [("Степень защиты IP54 подтверждена.", "bound"), ("Степень защиты IP44 подтверждена.", "insufficient")],
)
def test_ip_value_binding(evidence: str, expected: str):
    assert _result("Степень защиты не ниже IP54", evidence)["evidence_state"] == expected


def test_existing_legitimate_d04_2_binding_remains_supported():
    row = _result("Количество товара: 10 штук", "Поставка автоматических выключателей. Количество товара: 10 штук.")
    assert row["evidence_state"] == "bound"
    assert row["evidence_ids"] == ["FILE-01::document"]


def test_fail_closed_removes_unsupported_material_fields():
    row = _result("Сертификат происхождения из Италии", "Поставка выключателей без сведений о происхождении.")
    assert row == {
        "title": "INSUFFICIENT_EVIDENCE",
        "detail": "Не удалось привязать fallback-требование к конкретному документу закупки.",
        "source": "Документы закупки",
        "evidence_ids": [],
        "evidence_state": "insufficient",
    }


def test_mixed_rows_keep_completion_true():
    patched = _bind_fallback_evidence(
        _outputs(
            _row("Количество", "Количество товара: 10 штук"),
            _row("Срок", "Срок поставки: 15 дней"),
        ),
        documents=[_doc("Количество товара: 10 штук. Срок поставки: 20 дней.")],
    )
    rows = patched["requirements"]["requirements"]
    assert rows[0]["evidence_state"] == "bound"
    assert rows[1]["title"] == "INSUFFICIENT_EVIDENCE"
    assert patched["trace"]["fallback_evidence_binding_complete"] is True


def test_historical_p0_shape_does_not_bind_generic_contract_document():
    patched = _bind_fallback_evidence(
        _outputs(
            _row("Соответствие ГОСТ / ТУ", "Соответствие ГОСТ 31565-2012"),
            _row("Маркировка и безопасность", "Требования пожарной безопасности"),
            _row("Доставка до заказчика", "Поставка в течение 15 календарных дней"),
        ),
        documents=[_doc("Товар, продукция, требования, качество, поставка, маркировка и заказчик.")],
    )
    rows = patched["requirements"]["requirements"]
    assert [row["title"] for row in rows] == [
        "INSUFFICIENT_EVIDENCE",
        "INSUFFICIENT_EVIDENCE",
        "INSUFFICIENT_EVIDENCE",
    ]
    assert patched["trace"]["evidence_map"] == {}
    assert patched["trace"]["fallback_evidence_binding_complete"] is True


def test_semantic_matching_policy_is_traceable():
    patched = _bind_fallback_evidence(
        _outputs(_row("Количество", "Количество товара: 10 штук")),
        documents=[_doc("Количество товара: 10 штук")],
    )
    assert patched["trace"]["fallback_evidence_matching_policy"] == "semantic_concrete_v2"
