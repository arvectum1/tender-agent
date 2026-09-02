from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.modules.tender_operator_agent_demo import upload_service_legacy as legacy
from src.modules.tender_operator_agent_demo.router import router


def test_d04_3_run_api_exposes_persisted_goods_evidence_contract(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_CORP_TENDER_OPERATOR_DEMO_RUNS_DIR", str(tmp_path))
    run_id = "toa-run-d04-3-contract"
    legacy.ensure_demo_run_structure(run_id, exist_ok=True)

    metadata = {
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "mode": "procurement_search_intake",
        "tender_title": "Поставка автоматических выключателей",
        "tender_category": "44-ФЗ",
        "customer_name": "Тестовый заказчик",
        "status": "needs_review",
        "analysis_mode": "fallback_deterministic_adapter",
        "files": [],
        "limitations": [],
        "warnings": [],
        "human_in_the_loop": True,
        "external_actions": False,
        "no_platform_submission": True,
        "no_email_sending": True,
        "no_digital_signature": True,
        "procurement_source": "public_44fz",
        "procurement_id": "0123456789012345678",
        "attachments_status": "downloaded",
    }
    legacy._write_json(legacy._metadata_path(run_id), metadata)

    output_dir = legacy.get_demo_run_output_dir(run_id)
    evidence_id = "FILE-GOODS-1::document"
    legacy._write_json(
        output_dir / "requirements.json",
        {
            "requirements": [
                {
                    "title": "Количество товара",
                    "detail": "Количество товара: 10 штук.",
                    "source": "Техническое задание.txt",
                    "source_document": "Техническое задание.txt",
                    "evidence_ids": [evidence_id],
                    "evidence_state": "bound",
                }
            ],
            "analysis_context": {
                "procurement_category": "goods",
                "fallback_category": "GOODS",
                "grounding_policy": "source_bound_v1",
            },
        },
    )
    legacy._write_json(
        output_dir / "trace.json",
        {
            "overall_explanation": "Документ-зависимый fallback с concrete evidence binding.",
            "grounding_policy": "source_bound_v1",
            "fallback_category": "GOODS",
            "fallback_evidence_binding_policy": "goods_claim_evidence_binding_v1",
            "fallback_evidence_matching_policy": "semantic_concrete_v2",
            "fallback_evidence_binding_count": 1,
            "fallback_evidence_binding_complete": True,
            "evidence_map": {
                evidence_id: {
                    "file_id": "FILE-GOODS-1",
                    "source_document": "Техническое задание.txt",
                    "locator": "document",
                    "excerpt": "Количество товара: 10 штук.",
                }
            },
        },
    )
    legacy._write_json(
        output_dir / "final_recommendation.json",
        {
            "recommendation": "manual_review_required",
            "label": "нужна ручная проверка",
            "rationale": ["Проверить исходные документы."],
            "key_requirements": ["Количество товара"],
            "open_questions": [],
            "risks": [],
            "economics": [],
            "manual_checks": ["Сверить evidence."],
        },
    )
    (output_dir / "report.html").write_text("<html><body>ok</body></html>", encoding="utf-8")

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    # The production tampering harness performs an OpenAPI healthcheck. Guard
    # the dynamic response model at that exact serialization boundary too.
    openapi_response = client.get("/openapi.json")
    assert openapi_response.status_code == 200
    run_schema = openapi_response.json()["components"]["schemas"]["TenderOperatorUploadedRunResponse"]
    assert "runtime_analysis" in run_schema["properties"]

    response = client.get(f"/api/demo/tender-agent/runs/{run_id}")
    assert response.status_code == 200
    payload = response.json()

    # Existing UI contract stays backward compatible.
    assert isinstance(payload["final_recommendation"]["trace"], str)

    runtime = payload["runtime_analysis"]
    assert runtime["schema_version"] == "tender_operator_runtime_analysis_v1"
    assert runtime["procurement_category"] == "GOODS"
    assert runtime["grounding_policy"] == "source_bound_v1"
    assert runtime["fallback_category"] == "GOODS"
    assert runtime["fallback_evidence_binding_policy"] == "goods_claim_evidence_binding_v1"
    assert runtime["fallback_evidence_matching_policy"] == "semantic_concrete_v2"
    assert runtime["fallback_evidence_binding_complete"] is True
    assert runtime["evidence_map"][evidence_id]["file_id"] == "FILE-GOODS-1"
    assert runtime["requirements"][0]["evidence_ids"] == [evidence_id]
    assert runtime["requirements"][0]["evidence_state"] == "bound"
    assert runtime["trace"]["evidence_map"][evidence_id]["locator"] == "document"


def test_d04_3_run_response_remains_readable_without_persisted_analysis(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_CORP_TENDER_OPERATOR_DEMO_RUNS_DIR", str(tmp_path))
    run_id = "toa-run-d04-3-no-analysis"
    legacy.ensure_demo_run_structure(run_id, exist_ok=True)
    legacy._write_json(
        legacy._metadata_path(run_id),
        {
            "run_id": run_id,
            "created_at": datetime.now(UTC).isoformat(),
            "mode": "uploaded_demo",
            "tender_title": "Непроанализированный run",
            "tender_category": "44-ФЗ",
            "customer_name": "Тестовый заказчик",
            "status": "uploaded",
            "analysis_mode": "not_started",
            "files": [],
            "limitations": [],
            "warnings": [],
        },
    )
    output_dir = legacy.get_demo_run_output_dir(run_id)
    (output_dir / "report.html").write_text("<html><body>pending</body></html>", encoding="utf-8")

    response = legacy.get_uploaded_demo_run(run_id)

    assert response.runtime_analysis is None
    assert response.status.value == "uploaded"
