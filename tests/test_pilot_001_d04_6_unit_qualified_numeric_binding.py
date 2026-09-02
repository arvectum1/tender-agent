from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.modules.tender_operator_agent_demo.grounded_fallback_evidence_binding import (
    _bind_fallback_evidence,
)


def _doc(text: str):
    return SimpleNamespace(
        file_id="FILE-01",
        display_name="Спецификация.txt",
        text=text,
        evidence_chunks=[],
    )


def _result(claim: str, evidence: str) -> dict:
    outputs = {
        "requirements": {"requirements": [{"title": "Требование", "detail": claim}]},
        "trace": {"grounding_policy": "source_bound_v1", "fallback_category": "GOODS"},
    }
    return _bind_fallback_evidence(outputs, documents=[_doc(evidence)])[
        "requirements"
    ]["requirements"][0]


@pytest.mark.parametrize("evidence", ["Накопитель внутренних данных — 8 ТБ.", "Накопитель внутренних данных — 8 TB."])
def test_storage_capacity_exact_value_and_unit_binds(evidence: str):
    row = _result("Накопитель внутренних данных 8 ТБ", evidence)
    assert row["evidence_state"] == "bound"


@pytest.mark.parametrize("evidence", ["Накопитель внутренних данных — 4 ТБ.", "Накопитель внутренних данных — 3 ТБ.", "Накопитель внутренних данных — 8 ГБ.", "Накопитель внутренних данных — 8 МБ.", "Накопитель внутренних данных — 8 шт."])
def test_storage_capacity_wrong_value_or_unit_fails_closed(evidence: str):
    row = _result("Накопитель внутренних данных 8 ТБ", evidence)
    assert row["title"] == "INSUFFICIENT_EVIDENCE"
    assert row["evidence_ids"] == []


def test_historical_case_shape_with_unrelated_bare_eight_fails_closed():
    evidence = "Накопитель внутренних данных — 4 ТБ. Дополнительный накопитель — 3 ТБ. Количество портов — 8 шт."
    row = _result("Накопитель внутренних данных 8 ТБ", evidence)
    assert row["evidence_state"] == "insufficient"


def test_same_capacity_for_wrong_object_fails_closed():
    evidence = "Внутренний накопитель 4 ТБ. Система резервного копирования имеет отдельное хранилище 8 ТБ."
    row = _result("Накопитель внутренних данных 8 ТБ", evidence)
    assert row["title"] == "INSUFFICIENT_EVIDENCE"


def test_multiple_capacity_options_fail_closed_when_claim_is_not_explicitly_present():
    row = _result("Накопитель внутренних данных 8 ТБ", "Накопитель может поставляться в вариантах 3 ТБ, 4 ТБ.")
    assert row["evidence_state"] == "insufficient"


def test_exact_whole_document_match_stores_validated_excerpt():
    evidence = "Общие условия. " * 40 + "Накопитель внутренних данных — 8 ТБ."
    outputs = {
        "requirements": {"requirements": [{"title": "Требование", "detail": "Накопитель внутренних данных 8 ТБ"}]},
        "trace": {"grounding_policy": "source_bound_v1", "fallback_category": "GOODS"},
    }
    patched = _bind_fallback_evidence(outputs, documents=[_doc(evidence)])
    stored = patched["trace"]["evidence_map"]["FILE-01::document"]["excerpt"]
    assert "8 ТБ" in stored
    assert "Накопитель внутренних данных" in stored


def test_unknown_attached_unit_never_degrades_to_bare_number():
    row = _result("Накопитель внутренних данных 8 FOO", "Накопитель внутренних данных 8 FOO. Другой параметр 8.")
    assert row["title"] == "INSUFFICIENT_EVIDENCE"


def test_latin_cyrillic_capacity_normalization_is_same_unit_family():
    assert _result("Накопитель внутренних данных 8 TB", "Накопитель внутренних данных 8 ТБ.")["evidence_state"] == "bound"
    assert _result("Накопитель внутренних данных 8 ТБ", "Накопитель внутренних данных 8 TB.")["evidence_state"] == "bound"


@pytest.mark.parametrize("unit", ["КБ", "МБ", "ГБ", "ТБ", "KB", "MB", "GB", "TB", "KiB", "MiB", "GiB", "TiB"])
def test_storage_unit_families_are_parsed_without_bare_number_downgrade(unit: str):
    row = _result(f"Накопитель внутренних данных 8 {unit}", f"Накопитель внутренних данных 8 {unit}.")
    assert row["evidence_state"] == "bound"


def test_binary_and_decimal_storage_units_are_not_converted():
    row = _result("Накопитель внутренних данных 8 ТБ", "Накопитель внутренних данных 8 TiB.")
    assert row["title"] == "INSUFFICIENT_EVIDENCE"


def test_existing_days_positive_and_mismatch_remain_safe():
    assert _result("Срок поставки 15 календарных дней", "Срок поставки составляет 15 календарных дней.")["evidence_state"] == "bound"
    assert _result("Срок поставки 15 календарных дней", "Срок поставки составляет 20 календарных дней.")["title"] == "INSUFFICIENT_EVIDENCE"


def test_wrong_numeric_context_remains_fail_closed():
    row = _result("Срок поставки 15 дней", "Количество товара 15 шт.")
    assert row["evidence_state"] == "insufficient"


def test_mixed_supported_and_unsupported_rows_keep_binding_complete():
    outputs = {
        "requirements": {"requirements": [
            {"title": "Storage", "detail": "Накопитель внутренних данных 8 ТБ"},
            {"title": "Delivery", "detail": "Срок поставки 15 дней"},
        ]},
        "trace": {"grounding_policy": "source_bound_v1", "fallback_category": "GOODS"},
    }
    patched = _bind_fallback_evidence(
        outputs,
        documents=[_doc("Накопитель внутренних данных 8 ТБ. Срок поставки 20 дней.")],
    )
    rows = patched["requirements"]["requirements"]
    assert rows[0]["evidence_state"] == "bound"
    assert rows[1]["title"] == "INSUFFICIENT_EVIDENCE"
    assert patched["trace"]["fallback_evidence_binding_complete"] is True
