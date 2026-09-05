from types import SimpleNamespace

from src.modules.tender_operator_agent_demo.d09_scope_consistent_operator_output import _bind_operator_scope


def _rental_documents():
    return [
        SimpleNamespace(
            text="Арендодатель обязуется предоставить за плату во временное владение и пользование медицинское оборудование. Арендная плата установлена договором.",
            display_name="Проект контракта_аренда.doc",
            file_id="FILE-02",
            semantic_role="CONTRACT_DRAFT",
        )
    ]


def test_d09_rental_reconciles_operator_facing_service_semantics():
    outputs = {
        "requirements": {
            "preliminary_analysis": {
                "procurement_kind": "rental",
                "grounded_fallback_category": "SERVICES",
                "next_actions": [
                    "Проверить программу обучения, преподавателей и аудитории."
                ],
                "canonical_procurement_model": {"procurement_scope": "services"},
            },
            "analysis_context": {"procurement_category": "SERVICES"},
        },
        "trace": {"fallback_category": "SERVICES"},
        "final_recommendation": {
            "recommendation": "manual_review_required",
            "rationale": ["Подтвердить ресурсы для оказания услуг."],
            "open_questions": ["Какие преподаватели нужны?"],
        },
    }

    result = _bind_operator_scope(
        outputs,
        metadata={"tender_title": "Аренда медицинского оборудования"},
        documents=_rental_documents(),
    )
    preliminary = result["requirements"]["preliminary_analysis"]

    assert preliminary["procurement_kind"] == "rental"
    assert preliminary["scope"]["procurement_primary_scope"] == "rental"
    assert preliminary["grounded_fallback_category"] == "RENTAL"
    assert preliminary["canonical_procurement_model"]["procurement_scope"] == "rental"
    joined = " ".join(preliminary["next_actions"]).lower()
    assert "обучен" not in joined
    assert "преподав" not in joined
    assert "аудитор" not in joined
    assert "аренд" in joined
    assert result["trace"]["fallback_category"] == "RENTAL"
    assert result["requirements"]["analysis_context"]["procurement_category"] == "RENTAL"
    recommendation = result["final_recommendation"]
    assert recommendation["recommendation"] == "manual_review_required"
    assert all("преподав" not in value.lower() for value in recommendation["open_questions"])


def test_d09_goods_output_is_untouched():
    outputs = {
        "requirements": {
            "preliminary_analysis": {
                "procurement_kind": "goods",
                "grounded_fallback_category": "GOODS",
                "next_actions": ["Проверить срок поставки."],
                "canonical_procurement_model": {"procurement_scope": "goods"},
            }
        }
    }
    original = repr(outputs)
    docs = [
        SimpleNamespace(
            text="Поставщик обязуется поставить товар.",
            display_name="contract.docx",
            file_id="FILE-01",
            semantic_role="CONTRACT_DRAFT",
        )
    ]
    result = _bind_operator_scope(
        outputs,
        metadata={"tender_title": "Поставка товара"},
        documents=docs,
    )
    assert repr(result) == original
