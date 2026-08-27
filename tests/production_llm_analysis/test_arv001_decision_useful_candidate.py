from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

from scripts.arv001.build_decision_useful_candidate import (
    _decision_documents,
    derive_customer_model,
    render_decision_useful_report,
)
from scripts.arv001.complete_corpus_contract import DEFAULT_REGISTRY_NUMBER


def _analysis() -> dict:
    return {
        "technical": {
            "standards": ["ГОСТ 32511-2013", "ТР ТС 013/2011"],
            "specific_clauses": [
                {
                    "text": (
                        "Топливо дизельное зимнее экологического класса К5, "
                        "предельная температура фильтруемости не выше минус 32 °C."
                    ),
                    "source": "Техническое задание",
                    "locator": {"char_start": 10, "char_end": 130},
                },
                {
                    "text": "Цетановое число — не менее 51.",
                    "source": "Техническое задание",
                    "locator": {"char_start": 131, "char_end": 170},
                },
            ],
        },
        "contract": {
            "payment": [
                {
                    "text": (
                        "Оплата поставленного товара осуществляется в течение "
                        "7 рабочих дней с даты подписания документа о приемке. "
                        "Аванс не предусмотрен."
                    ),
                    "source": "Проект контракта",
                }
            ],
            "security": [
                {
                    "text": (
                        "Размер обеспечения исполнения Контракта составляет 5 % "
                        "от цены Контракта; обеспечение предоставляется независимой "
                        "гарантией или внесением денежных средств."
                    ),
                    "source": "Проект контракта",
                }
            ],
            "acceptance": [
                {
                    "text": (
                        "Приемка осуществляется в течение 5 рабочих дней с даты "
                        "поступления документа о приемке."
                    ),
                    "source": "Проект контракта",
                }
            ],
            "liability": [
                {
                    "text": (
                        "Пеня начисляется за каждый день просрочки в размере "
                        "1/300 ключевой ставки от не уплаченной в срок суммы."
                    ),
                    "source": "Проект контракта",
                },
                {
                    "text": (
                        "Штраф за ненадлежащее исполнение обязательства составляет "
                        "1 процент от цены Контракта."
                    ),
                    "source": "Проект контракта",
                },
            ],
            "termination": [
                {
                    "text": (
                        "Заказчик вправе принять решение об одностороннем отказе "
                        "от исполнения Контракта в предусмотренных законом случаях."
                    ),
                    "source": "Проект контракта",
                }
            ],
            "liability_cap": [
                {
                    "text": (
                        "Общая сумма начисленных штрафов не может превышать "
                        "цену Контракта."
                    ),
                    "source": "Проект контракта",
                }
            ],
            "liability_cap_status": "found",
        },
        "application_requirements": [
            {
                "text": (
                    "Заявка должна содержать декларацию о соответствии участника "
                    "единым требованиям."
                ),
                "source": "Требования к составу заявки",
            }
        ],
    }


def _model() -> dict:
    logical_documents = [
        {
            "name": "Извещение о закупке",
            "type": "извещение",
            "kind": "notice",
        },
        {
            "name": "Приложение 1 Описание объекта закупки",
            "type": "техническая документация",
            "kind": "technical_specification",
        },
        {
            "name": "Приложение 2 Обоснование НМЦК",
            "type": "ценовое обоснование",
            "kind": "price_justification",
        },
        {
            "name": "Приложение 3 Требования к составу заявки",
            "type": "требования к заявке",
            "kind": "application_requirements",
        },
        {
            "name": "Приложение 4 Проект контракта",
            "type": "проект контракта",
            "kind": "contract_draft",
        },
        {
            "name": "Приложение 5 Реквизиты обеспечения исполнения контракта",
            "type": "обеспечение исполнения контракта",
            "kind": "contract_performance_security",
        },
    ]
    return {
        "ai_runtime_provenance": {"producer": "production_llm_r10_1"},
        "procurement_number": DEFAULT_REGISTRY_NUMBER,
        "procurement_title": "Поставка дизельного топлива",
        "customer_name": "Заказчик",
        "publication_datetime": "2026-07-02T12:21:00+12:00",
        "publication_datetime_display": "02.07.2026 12:21 (UTC+12)",
        "application_deadline": "2026-07-10T18:30:00+12:00",
        "application_deadline_display": "10.07.2026 18:30 (UTC+12)",
        "analysis_as_of_iso": "2026-08-27T06:50:02+03:00",
        "analysis_as_of": "27.08.2026 06:50 (UTC+3)",
        "nmck": "25 200 000",
        "delivery_place": "Архангельск",
        "customer_decision": {
            "recommendation": "Статус срока подачи не определён",
            "reasons": ["Основные реквизиты закупки подтверждены."],
            "confirmed": ["позиция и количество"],
            "next_action": "Сверить документы.",
        },
        "line_items": [
            {
                "sequence": 1,
                "original_name": "Топливо дизельное",
                "quantity_display": "140",
                "quantity": 140,
                "unit_original": "т",
                "unit_normalized": "т",
                "okpd2": "19.20.21.300",
                "characteristics": [],
                "source_row": 1,
                "evidence_ids": ["ev-1"],
            }
        ],
        "okpd2_codes": [{"code": "19.20.21.300", "name": "Топливо дизельное"}],
        "requirements": [
            {
                "title": "Соответствие ГОСТ / ТУ",
                "detail": (
                    "Товар должен соответствовать ГОСТ, ТУ и иной действующей "
                    "нормативной документации."
                ),
                "type": "техническое требование",
                "source": "Техническое задание",
            },
            {
                "title": "Сертификаты и паспорт качества",
                "detail": "Нужны документы качества по применимым позициям.",
                "type": "техническое требование",
                "source": "Техническое задание",
            },
        ],
        "compatibility_sections": {
            "contract_highlights": [
                "Проект контракта содержит условия оплаты.",
                "Цена контракта: твердая, без индексации на период исполнения.",
            ]
        },
        "metadata": {
            "document_set_summary": {
                "status": "complete",
                "logical_document_count": 6,
                "physical_file_count": 10,
                "logical_documents": logical_documents,
            }
        },
        "evidence_map": [
            {
                "evidence_id": "ev-1",
                "document": "Извещение о закупке",
                "row": 1,
                "short_excerpt": "Топливо дизельное",
                "related_items": ["line-1"],
            }
        ],
        "risks": [],
        "customer_questions": [],
        "corpus_limitations": [],
        "sentinel": {"must_remain": "unchanged"},
    }


def test_derived_model_replaces_generic_content_without_mutating_canonical() -> None:
    model = _model()
    original = deepcopy(model)
    derived = derive_customer_model(model, _analysis())

    assert model == original
    assert derived is not model
    requirements = "\n".join(
        f"{row.get('title')} {row.get('detail')}" for row in derived["requirements"]
    )
    assert "ГОСТ 32511-2013" in requirements
    assert "ТР ТС 013/2011" in requirements
    assert "экологического класса К5" in requirements
    assert "Цетановое число" in requirements
    assert "Заявка должна содержать декларацию" in requirements
    assert "Товар должен соответствовать ГОСТ, ТУ и иной" not in requirements

    contract = "\n".join(
        derived["compatibility_sections"]["contract_highlights"]
    )
    assert "7 рабочих дней" in contract
    assert "Аванс не предусмотрен" in contract
    assert "5 %" in contract
    assert "независимой гарантией" in contract
    assert "1/300 ключевой ставки" in contract
    assert "1 процент от цены Контракта" in contract
    assert "Общая сумма начисленных штрафов" in contract
    assert "Проект контракта содержит условия оплаты." not in contract


def test_rendered_candidate_is_decision_useful_and_customer_safe() -> None:
    derived = derive_customer_model(_model(), _analysis())
    rendered = render_decision_useful_report(
        derived,
        expected_registry_number=DEFAULT_REGISTRY_NUMBER,
    )

    assert "ГОСТ 32511-2013" in rendered
    assert "экологического класса К5" in rendered
    assert "Цетановое число" in rendered
    assert "7 рабочих дней" in rendered
    assert "Аванс не предусмотрен" in rendered
    assert "5 %" in rendered
    assert "независимой гарантией" in rendered
    assert "1/300 ключевой ставки" in rendered
    assert "1 процент от цены Контракта" in rendered
    assert "Общая сумма начисленных штрафов" in rendered
    assert "Заявка должна содержать декларацию" in rendered
    assert "Проект контракта содержит условия оплаты." not in rendered
    assert "Предварительная рекомендация:" in rendered
    assert "Контроль перед коммерческим решением" in rendered
    assert "Product Owner" not in rendered
    assert "NOT_AUTHORIZED" not in rendered


def test_prepared_document_adapter_recognizes_frozen_document_kinds() -> None:
    prepared = [
        SimpleNamespace(
            document_kind="technical_specification",
            original_name="Приложение 1 Описание объекта закупки.docx",
            text="ГОСТ 32511-2013, класс К5",
        ),
        SimpleNamespace(
            document_kind="contract_draft",
            original_name="Приложение 4 Проект контракта.docx",
            text="Оплата в течение 7 рабочих дней.",
        ),
        SimpleNamespace(
            document_kind="application_requirements",
            original_name="Приложение 3 Требования к составу заявки.docx",
            text="Заявка должна содержать декларацию.",
        ),
    ]
    documents = _decision_documents(prepared)
    assert [item.role for item in documents] == [
        "technical_spec",
        "contract_draft",
        "application_requirements",
    ]
    assert documents[0].display_name.startswith("Приложение 1")
