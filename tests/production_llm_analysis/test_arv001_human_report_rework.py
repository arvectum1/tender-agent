from __future__ import annotations

from copy import deepcopy

import pytest

from scripts.arv001.complete_corpus_contract import (
    DEFAULT_REGISTRY_NUMBER,
    AcceptanceBlocked,
)
from scripts.arv001 import rework_human_report


def _accepted_report_html(extra: str = "") -> str:
    return f"""<!doctype html><html lang="ru"><body><main>
<section><h1>Анализ закупки № {DEFAULT_REGISTRY_NUMBER}</h1>
<p>Дизельное топливо; количество 140; НМЦК 25 200 000 ₽; ОКПД2 19.20.21.300.</p>
<p>Описание объекта закупки и технические требования подтверждены.</p>
<p>Проект контракта содержит условия оплаты, приемки, обеспечения и ответственности.</p>
</section>
<section class="decision"><h2>Решение: HOLD</h2><p>{extra}</p></section>
</main></body></html>"""


def _r10_model() -> dict:
    return {
        "ai_runtime_provenance": {
            "producer": "production_llm_r10_1",
        },
        "sentinel": {"must_remain": "unchanged"},
    }


def test_report_rework_separates_quality_from_human_governance(monkeypatch) -> None:
    model = _r10_model()
    snapshot = deepcopy(model)
    monkeypatch.setattr(
        rework_human_report,
        "_render_customer_report_html",
        lambda _model: _accepted_report_html("&lt;script&gt;alert(1)&lt;/script&gt;"),
    )

    rendered = rework_human_report.rework_canonical_report(
        model,
        expected_registry_number=DEFAULT_REGISTRY_NUMBER,
    )

    assert model == snapshot
    assert "Техническое качество:</strong> PASSED" in rendered
    assert "Quality evidence:</strong> EXISTS" in rendered
    assert "Product Owner:</strong> REJECTED" in rendered
    assert "REPORT_REWORK_REQUIRED" in rendered
    assert "Independent review:</strong> NOT_AUTHORIZED" in rendered
    assert "Freeze:</strong> NOT_ALLOWED" in rendered
    assert "P8.05 / внешний источник:</strong> BLOCKED_EXTERNAL_SOURCE" in rendered
    assert "Рекомендация по закупке: HOLD" in rendered
    assert '<h2>Решение: HOLD</h2>' not in rendered
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered
    assert "<script>alert(1)</script>" not in rendered


def test_report_rework_fails_closed_on_independent_review_readiness(monkeypatch) -> None:
    monkeypatch.setattr(
        rework_human_report,
        "_render_customer_report_html",
        lambda _model: _accepted_report_html("Ready for independent review"),
    )

    with pytest.raises(
        AcceptanceBlocked,
        match="arv001_independent_review_readiness_forbidden",
    ):
        rework_human_report.rework_canonical_report(
            _r10_model(),
            expected_registry_number=DEFAULT_REGISTRY_NUMBER,
        )


def test_report_rework_rejects_non_r10_canonical_input() -> None:
    with pytest.raises(AcceptanceBlocked, match="canonical_report_not_r10_1"):
        rework_human_report.rework_canonical_report(
            {"ai_runtime_provenance": {"producer": "frozen_r9"}},
            expected_registry_number=DEFAULT_REGISTRY_NUMBER,
        )
